#!/usr/bin/env python3
"""Generá un inventario o validá el libro extraído por el agente."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.tif', '.tiff', '.pdf'}
CHECKS = ('documento_valido', 'destinatario_valido', 'financiacion_valida',
          'pago_verificado', 'categoria_admitida', 'sin_doble_deduccion')
ORDINARY = {'alimentacion', 'vestimenta', 'alquiler', 'mantenimiento', 'equipamiento',
            'salud', 'educacion', 'movilidad', 'recreacion', 'actividad'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def inventory(path):
    path = Path(path).resolve(strict=True)
    files = sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
    return {'archivos': [{'archivo': str(p), 'sha256': digest(p), 'bytes': p.stat().st_size}
                         for p in files if p.suffix.lower() in EXTENSIONS],
            'omitidos': [str(p) for p in files if p.suffix.lower() not in EXTENSIONS]}


def money(value):
    return type(value) is int and value >= 0


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def identities(doc):
    keys = []
    if doc.get('cdc'):
        keys.append('cdc:' + str(doc['cdc']))
    fields = ('ruc_emisor', 'tipo', 'timbrado', 'numero')
    if all(doc.get(k) for k in fields):
        keys.append('doc:' + '|'.join(str(doc[k]).strip() for k in fields))
    return keys


def build(data):
    p = data['perfil']
    year = p['ejercicio']
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError('ejercicio inválido')
    start = parse_date(p.get('inicio_deducciones'))
    docs = data['documentos']
    ids = [d['id'] for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError('los id de filas deben ser únicos')
    groups = defaultdict(list)
    for i, d in enumerate(docs):
        for key in identities(d):
            groups[key].append(i)
    # Una copia puede tener CDC y otra sólo timbrado
    parent = list(range(len(docs)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for indices in groups.values():
        for i in indices[1:]:
            parent[root(i)] = root(indices[0])
    components = defaultdict(list)
    for i in range(len(docs)):
        components[root(i)].append(i)
    duplicates, conflicts = set(), set()
    compare = ('total_gs', 'fecha', 'moneda', 'concepto', 'pagos', 'decision',
               'candidato_gs', 'iva_credito_gs', 'otro_impuesto_gs', 'controles',
               'ruc_emisor', 'ruc_destinatario', 'numero', 'timbrado', 'origen',
               'condicion', 'pais', 'gravado_10_gs', 'gravado_5_gs', 'exento_gs', 'imputaciones')
    for indices in components.values():
        if len(indices) < 2:
            continue
        base = docs[indices[0]]
        if any(any(docs[i].get(k) != base.get(k) for k in compare) for i in indices[1:]):
            conflicts.update(indices)
        else:
            duplicates.update(indices[1:])
    adjusted = {d.get('factura_asociada') for d in docs
                if d.get('tipo') in {'nota_credito', 'nota_debito'}}
    adjusted_groups = {root(i) for i, d in enumerate(docs)
                       if d['id'] in adjusted or any(k in adjusted for k in identities(d))}
    rows = []
    for i, d in enumerate(docs):
        problems = []
        total, candidate = d.get('total_gs'), d.get('candidato_gs')
        vat, other = d.get('iva_credito_gs'), d.get('otro_impuesto_gs')
        issue = parse_date(d.get('fecha'))
        if not start or start.year != year:
            problems.append('falta inicio de deducciones confirmado para el ejercicio')
        if p.get('normativa_verificada') is not True or not p.get('fuentes_vigencia'):
            problems.append('falta verificar normativa del ejercicio')
        if not p.get('ruc_titular') or type(p.get('contribuyente_iva')) is not bool:
            problems.append('perfil tributario incompleto')
        if not issue:
            problems.append('fecha ilegible o inválida')
        if not money(total) or total == 0:
            problems.append('total inválido o faltante')
        if not identities(d):
            problems.append('identidad documental incompleta')
        if d.get('origen') not in {'preimpreso', 'electronico', 'virtual', 'otro'}:
            problems.append('origen documental sin identificar')
        for source in d.get('fuentes', []):
            try:
                if digest(source['archivo']) != source['sha256']:
                    problems.append('el original cambió desde la extracción')
            except (KeyError, OSError):
                problems.append('original sin respaldo verificable')
        if not d.get('fuentes'):
            problems.append('falta el original')
        if d.get('observaciones'):
            problems.extend(d['observaciones'])
        if i in conflicts:
            problems.append('duplicados con datos contradictorios, conciliá ambos')
        if root(i) in adjusted_groups:
            problems.append('factura con ajuste vinculado pendiente de conciliación')
        if d.get('tipo') != 'factura' or d.get('condicion') != 'contado':
            problems.append('documento especial, ajuste o crédito: conciliación específica')
        if d.get('moneda') != 'PYG' or d.get('pais') != 'PY':
            problems.append('moneda o operación extranjera: revisión específica')
        if d.get('categoria') not in ORDINARY:
            problems.append('categoría con revisión específica')
        if not d.get('motivo') or not d.get('norma_url') or not d.get('articulo'):
            problems.append('falta fundamento fiscal')
        decision = d.get('decision')
        amount = None
        if decision == 'deducible':
            for check in CHECKS:
                if d.get('controles', {}).get(check) is not True:
                    problems.append('falta verificar ' + check)
            if not all(money(v) for v in (candidate, vat, other)):
                problems.append('faltan importes de la porción deducible y exclusiones')
            elif money(total) and (candidate > total or vat + other > candidate):
                problems.append('importes incompatibles con total o porción admisible')
            payments = d.get('pagos', [])
            paid = 0
            for pay in payments:
                dt = parse_date(pay.get('fecha'))
                if not dt or not money(pay.get('monto_gs')) or not pay.get('respaldo'):
                    problems.append('pago incompleto')
                elif start and start <= dt <= date(year, 12, 31):
                    paid += pay['monto_gs']
            if not payments:
                problems.append('falta evidencia de pago')
            if money(candidate) and candidate > paid:
                problems.append('porción superior a pagos del período deducible')
            if issue and start and issue < start:
                problems.append('emisión anterior al inicio: revisá su tratamiento')
            if issue and issue.year > year:
                problems.append('documento posterior al ejercicio')
            if not problems:
                amount = candidate - vat - other
        elif decision == 'no_deducible':
            # El rechazo fiscal no requiere acreditar un pago
            if not problems:
                amount = 0
        else:
            problems.append('decisión fiscal pendiente')
        status = 'revisar' if problems else decision
        if i in duplicates and i not in conflicts:
            status, amount = 'duplicado', None
        route = ('ya registrado' if d.get('ya_registrado') is True else
                 'recuperar en Marangatu' if d.get('origen') in {'electronico', 'virtual'}
                 else 'manual o importación oficial')
        rows.append({**d, 'estado': status, 'deducible_gs': amount if status != 'revisar' else None,
                     'pendientes': sorted(set(problems)), 'ruta_carga': route})
    return {'perfil': p, 'documentos': rows, 'resumen': {
        'filas': len(rows), 'estados': dict(Counter(r['estado'] for r in rows)),
        'deducible_identificado_gs': sum(r['deducible_gs'] or 0 for r in rows),
        'alcance': 'subtotal revisado de este libro, no impuesto anual ni declaración presentada'}}


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inv = sub.add_parser('inventario')
    inv.add_argument('ruta')
    inv.add_argument('--out', required=True)
    book = sub.add_parser('libro')
    book.add_argument('json')
    book.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    if args.command == 'inventario':
        result = inventory(args.ruta)
        write_json(args.out, result)
        print(f"archivos: {len(result['archivos'])}, omitidos: {len(result['omitidos'])}")
    else:
        result = build(json.loads(Path(args.json).read_text()))
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / 'libro.json', result)
        fields = ('id', 'fecha', 'ruc_emisor', 'numero', 'concepto', 'total_gs',
                  'deducible_gs', 'estado', 'ruta_carga', 'motivo', 'norma_url', 'pendientes')
        with (out / 'libro-interno.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            for row in result['documentos']:
                writer.writerow(safe_cell('; '.join(row[k]) if k == 'pendientes' else row.get(k))
                                for k in fields)
        print(json.dumps(result['resumen'], ensure_ascii=False))


if __name__ == '__main__':
    main()
