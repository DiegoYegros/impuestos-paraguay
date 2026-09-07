"""Validá el archivo de trabajo y conciliá reportes de Marangatu."""
import argparse
import hashlib
import html
import json
import re
import threading
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from facturas import build, digest, identities, money, safe_cell

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
HEADERS = ['id', 'fecha', 'emisor', 'número', 'concepto', 'total Gs', 'deducible Gs',
           'estado', 'motivo / pendiente', 'carga', 'original', 'norma']
FIELDS = ('ruc_emisor', 'ruc_destinatario', 'fecha', 'tipo', 'origen', 'timbrado',
          'numero', 'cdc', 'moneda', 'condicion', 'total_gs', 'gravado_10_gs',
          'gravado_5_gs', 'exento_gs', 'imputaciones')
LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc)


def engine_version():
    return digest(__file__) + digest(Path(__file__).with_name('facturas.py'))


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('la fecha de consulta debe incluir zona horaria')
    return dt


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def xlsx_cells(path):
    """Leé valores y fórmulas sin ejecutar contenido del XLSX."""
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 50_000_000:
            raise ValueError('planilla demasiado grande para esta validación')
        names = z.namelist()
        if any('externalLink' in n or 'vbaProject' in n for n in names):
            raise ValueError('planilla con vínculos externos o macros')
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = [''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets = {r.get('Id'): r.get('Target') for r in rels}
        if any(r.get('TargetMode') == 'External' for r in rels):
            raise ValueError('referencia externa en el libro')
        book = ET.fromstring(z.read('xl/workbook.xml'))
        prop = book.find('m:workbookPr', NS)
        if prop is not None and prop.get('date1904') in {'1', 'true'}:
            raise ValueError('sistema de fechas 1904 no admitido')
        sheets = {}
        for sheet in book.findall('m:sheets/m:sheet', NS):
            rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            target = targets[rid]
            target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            cells = {}
            for c in ET.fromstring(z.read(target)).findall('.//m:sheetData/m:row/m:c', NS):
                text = c.findtext('m:v', default=None, namespaces=NS)
                kind = c.get('t')
                if kind == 's':
                    value = shared[int(text)]
                elif kind == 'inlineStr':
                    value = ''.join(c.find('m:is', NS).itertext())
                elif kind in {'str', 'd', 'e'}:
                    value = text
                elif text is not None:
                    value = float(text)
                else:
                    value = None
                cells[c.get('r')] = (value, c.findtext('m:f', namespaces=NS), kind)
            sheets[sheet.get('name')] = cells
        return sheets


def check_workbook(path, book):
    sheets = xlsx_cells(path)
    cells = sheets['Facturas']
    for i, expected in enumerate(HEADERS):
        if cells.get(f'{chr(65 + i)}5', (None,))[0] != expected:
            raise ValueError('encabezados de Facturas distintos al formato validado')
    expected_rows = []
    for d in book['documentos']:
        dt = datetime.fromisoformat(d['fecha']) if d.get('fecha') else None
        serial = (dt - datetime(1899, 12, 30)).days + 0.5 if dt else None
        expected_rows.append([
            d['id'], serial, d.get('emisor') or d.get('ruc_emisor'), d.get('numero'),
            d.get('concepto'), d.get('total_gs'), d.get('deducible_gs'), d['estado'],
            ' · '.join(filter(None, [d.get('motivo'), *d.get('pendientes', [])])),
            d['ruta_carga'], ' · '.join(f"{s['archivo']} {s.get('ubicacion', '')}"
                                      for s in d.get('fuentes', [])),
            f"{d.get('articulo') or ''} {d.get('norma_url') or ''}"])
    # Compará por id para permitir ordenar la tabla sin cambiar su contenido
    expected_by_id = {r[0]: [safe_cell(v) for v in r] for r in expected_rows}
    actual_by_id = {}
    row_numbers = sorted({int(re.search(r'\d+$', addr)[0]) for addr, (v, f, _) in cells.items()
                          if (v is not None or f is not None) and int(re.search(r'\d+$', addr)[0]) >= 6})
    if row_numbers != list(range(6, len(expected_rows) + 6)):
        raise ValueError('filas agregadas, faltantes o fuera del rango del subtotal')
    if any(re.match('[A-Z]+', addr)[0] not in list('ABCDEFGHIJKL') for addr, (v, f, _) in cells.items()
           if (v is not None or f is not None) and int(re.search(r'\d+$', addr)[0]) >= 6):
        raise ValueError('columnas adicionales en los datos de Facturas')
    for n in row_numbers:
        row = []
        for i in range(12):
            value, formula, kind = cells.get(f'{chr(65 + i)}{n}', (None, None, None))
            if formula is not None or kind == 'e':
                raise ValueError(f'fila {n} con fórmula o error en datos de Facturas')
            row.append(value)
        if not row[0] or row[0] in actual_by_id:
            raise ValueError(f'fila {n} sin id o con id duplicado')
        actual_by_id[row[0]] = row
    if actual_by_id != expected_by_id:
        changed = sorted(str(k) for k in actual_by_id.keys() | expected_by_id.keys()
                         if actual_by_id.get(k) != expected_by_id.get(k))
        raise ValueError('filas distintas de la extracción verificada: ' + ', '.join(changed))
    load = sheets['Carga']
    load_fields = ('id', *FIELDS)
    for i, key in enumerate(load_fields):
        if load.get(f'{chr(65 + i)}1', (None,))[0] != key:
            raise ValueError('encabezados de Carga distintos al formato validado')
    load_expected = {}
    for d in book['documentos']:
        record = {'id': d['id'], **fiscal(d)}
        record['imputaciones'] = ','.join(record['imputaciones']) if isinstance(record['imputaciones'], list) else None
        load_expected[d['id']] = [safe_cell(record[k]) for k in load_fields]
    load_actual = {}
    load_rows = sorted({int(re.search(r'\d+$', a)[0]) for a, (v, f, _) in load.items()
                        if (v is not None or f is not None) and int(re.search(r'\d+$', a)[0]) > 1})
    if load_rows != list(range(2, len(expected_rows) + 2)):
        raise ValueError('filas agregadas o faltantes en Carga')
    if any(re.match('[A-Z]+', a)[0] not in list('ABCDEFGHIJKLMNOP') for a, (v, f, _) in load.items()
           if v is not None or f is not None):
        raise ValueError('columnas adicionales en Carga')
    for n in load_rows:
        values = [load.get(f'{chr(65 + i)}{n}', (None, None, None)) for i in range(len(load_fields))]
        if any(f is not None or k == 'e' for _, f, k in values):
            raise ValueError('fórmula o error en la hoja Carga')
        row = [v for v, _, _ in values]
        if not row[0] or row[0] in load_actual:
            raise ValueError('id vacío o duplicado en la hoja Carga')
        load_actual[row[0]] = row
    if load_actual != load_expected:
        raise ValueError('la hoja Carga difiere de la extracción verificada')
    value, formula, kind = sheets['Resumen'].get('B5', (None, None, None))
    last = max(6, len(expected_rows) + 5)
    if formula != f'SUM(Facturas!G6:G{last})' or kind == 'e':
        raise ValueError('fórmula del subtotal modificada')
    if value != book['resumen']['deducible_identificado_gs']:
        raise ValueError('subtotal de la planilla sin recalcular o diferente del libro')


def fiscal(doc):
    result = {k: doc.get(k) for k in FIELDS}
    if isinstance(result['imputaciones'], list):
        result['imputaciones'] = sorted(result['imputaciones'])
    return result


def record_errors(d):
    errors = []
    if not identities(d):
        errors.append('falta identidad fiscal')
    for field in ('ruc_emisor', 'ruc_destinatario', 'fecha', 'tipo', 'origen', 'moneda', 'condicion'):
        if not isinstance(d.get(field), str) or not d[field].strip():
            errors.append('falta ' + field)
    for field in ('ruc_emisor', 'ruc_destinatario'):
        if not re.fullmatch(r'\d{1,9}-\d', str(d.get(field, ''))):
            errors.append('formato inválido de ' + field)
    if d.get('origen') == 'electronico':
        if not re.fullmatch(r'\d{44}', str(d.get('cdc', ''))):
            errors.append('CDC incompleto')
    if not re.fullmatch(r'\d{8}', str(d.get('timbrado', ''))) or not re.fullmatch(
            r'\d{3}-\d{3}-\d{7}', str(d.get('numero', ''))):
        errors.append('timbrado o número incompleto')
    try:
        if datetime.fromisoformat(d['fecha']).strftime('%Y-%m-%d') != d['fecha']:
            errors.append('fecha inválida')
    except (KeyError, ValueError, TypeError):
        errors.append('fecha inválida')
    parts = [d.get(k) for k in ('gravado_10_gs', 'gravado_5_gs', 'exento_gs')]
    if not all(money(v) for v in [d.get('total_gs'), *parts]) or sum(parts) != d.get('total_gs'):
        errors.append('total distinto de gravadas más exentas, o importes incompletos')
    taxes = d.get('imputaciones')
    if not isinstance(taxes, list) or not taxes or len(taxes) != len(set(taxes)) or any(
            t not in {'IRP', 'IVA', 'IRE', 'NO_IMPUTAR'} for t in taxes):
        errors.append('imputaciones incompletas o inválidas')
    return errors


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        repo = Path(__file__).resolve().parents[3]
        if self.root.is_relative_to(repo):
            raise ValueError('guardá los datos fuera del repositorio')

    def path(self, value):
        path = Path(value)
        path = (self.root / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('archivo fuera del directorio de datos')
        return path

    def folder(self, lot):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', lot):
            raise ValueError('identificador de lote inválido')
        return self.path(lot)

    def read(self, path, hashes):
        path = self.path(path)
        raw = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('número inválido')))

    def evidence(self, source, hashes):
        path = self.path(source['archivo'])
        sha = digest(path)
        hashes[str(path)] = sha
        if sha != source['sha256']:
            raise ValueError('cambió un archivo de respaldo')

    def report(self, folder, phase, profile, hashes, after=None):
        data = self.read(folder / f'marangatu-{phase}.json', hashes)
        if data.get('ruc_titular') != profile['ruc_titular'] or data.get('ejercicio') != profile['ejercicio']:
            raise ValueError('reporte de otro titular o ejercicio')
        if data.get('completo') is not True or data.get('cotejado_con_original') is not True:
            raise ValueError('reporte incompleto o sin cotejar con la descarga original')
        dt = timestamp(data['consultado_en'])
        if now() - dt > timedelta(hours=24) or dt > now() + timedelta(minutes=5):
            raise ValueError('reporte vencido o con fecha futura')
        if after and dt <= timestamp(after):
            raise ValueError('el reporte posterior debe ser nuevo, después de validar')
        self.evidence(data['fuente'], hashes)
        docs = data['documentos']
        if data.get('cantidad') != len(docs) or any(record_errors(d) for d in docs):
            raise ValueError('reporte con filas incompletas o cantidad incorrecta')
        if data.get('total_gs') != sum(d['total_gs'] for d in docs):
            raise ValueError('total del reporte distinto de sus filas')
        if any(not d.get('referencia_original') for d in docs):
            raise ValueError('faltan referencias a las filas del reporte original')
        if any(d.get('estado_registro') not in {'registrado', 'confirmado'} for d in docs):
            raise ValueError('el reporte incluye filas sin registro aceptado')
        if any(not d['fecha'].startswith(str(profile['ejercicio']) + '-') for d in docs):
            raise ValueError('reporte con facturas de otro ejercicio')
        return data

    def persist(self, folder, name, result):
        history = self.path(folder / 'historial')
        history.mkdir(mode=0o700, parents=True, exist_ok=True)
        save(history / f'{result["id"]}.json', result)
        save(self.path(folder / f'{name}.json'), result)
        self.render(folder, result)
        return result

    def render(self, folder, result):
        esc = lambda v: html.escape(str(v), quote=True)
        rows = []
        for d in result['facturas']:
            links = ' '.join(f'<a href="{esc(self.path(s["archivo"]).as_uri())}">original</a>'
                             for s in d.get('fuentes', []))
            rows.append('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in
                        [d['id'], d['estado_carga'], d.get('numero', ''),
                         d.get('total_gs', ''), '; '.join(d['motivos'])]) + f'<td>{links}</td></tr>')
        issues = ''.join(f'<li>{esc(e)}</li>' for e in result['errores'])
        document = ('<!doctype html><html lang="es"><meta charset="utf-8"><title>revisión de facturas</title>'
                    '<style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 20px}'
                    'table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;'
                    'text-align:left}th{background:#eee}li{margin:8px}</style>'
                    f'<h1>revisión de facturas</h1><p>{esc(result["creado_en"])} · {esc(result["fase"])}</p>'
                    '<p>corregí el dato o agregá su respaldo en la extracción, regenerá la planilla y validá de nuevo</p>'
                    f'<ul>{issues}</ul><table><tr><th>id</th><th>estado</th><th>número</th>'
                    '<th>Gs</th><th>qué revisar</th><th>comprobante</th></tr>' + ''.join(rows) + '</table></html>')
        self.path(folder / 'revision.html').write_text(document, encoding='utf-8')

    def validate(self, lot):
        with LOCK:
            folder, hashes, errors = self.folder(lot), {}, []
            raw = self.read(folder / 'extraccion.json', hashes)
            try:
                inventory = self.read(folder / 'inventario.json', hashes)
                originals = set()
                for src in inventory['archivos']:
                    self.evidence(src, hashes)
                    originals.add(str(self.path(src['archivo'])))
                referenced = {str(self.path(s['archivo'])) for d in raw['documentos'] for s in d.get('fuentes', [])}
                if originals != referenced:
                    errors.append('hay originales sin procesar o documentos fuera del inventario')
            except (ValueError, OSError, KeyError) as e:
                errors.append('inventario: ' + str(e))
            for d in raw['documentos']:
                for src in d.get('fuentes', []):
                    self.path(src['archivo'])
                    try:
                        self.evidence(src, hashes)
                    except (ValueError, OSError, KeyError) as e:
                        errors.append(str(e))
            book = build(raw)
            try:
                sheet = self.path(folder / 'facturas-irp.xlsx')
                hashes[str(sheet)] = digest(sheet)
                check_workbook(sheet, book)
            except (ValueError, OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
                errors.append('planilla: ' + str(e))
            report = None
            try:
                report = self.report(folder, 'antes', book['perfil'], hashes)
                previous = self.path(folder / 'conciliacion.json')
                if previous.exists():
                    last = self.read(previous, {})
                    if timestamp(report['consultado_en']) <= timestamp(last['creado_en']):
                        errors.append('actualizá el reporte previo después de la última conciliación antes de reintentar')
            except (ValueError, OSError, KeyError) as e:
                errors.append('Marangatu: ' + str(e))
            rows = []
            for d in book['documentos']:
                reasons = list(d['pendientes'])
                reasons.extend(record_errors(d))
                if d.get('cotejo_original', {}).get('verificado') is not True or not d.get('cotejo_original', {}).get('evidencia'):
                    reasons.append('falta segunda lectura contra el comprobante original')
                if d.get('estado') not in {'deducible', 'duplicado'}:
                    reasons.append('tratamiento fiscal pendiente de revisión para este flujo de carga')
                if d.get('imputaciones') != ['IRP']:
                    reasons.append('imputación múltiple o distinta de IRP requiere revisión')
                matches = [r for r in report['documentos'] if set(identities(d)) & set(identities(r))] if report else []
                if len(matches) > 1:
                    reasons.append('varias filas del portal coinciden con esta factura')
                elif matches and fiscal(matches[0]) != fiscal(d):
                    reasons.append('diferencias con el portal: ' + ', '.join(k for k in FIELDS if fiscal(matches[0])[k] != fiscal(d)[k]))
                if d.get('ya_registrado') is True and not matches:
                    reasons.append('la extracción dice registrado, pero no aparece en el reporte')
                status = 'cargada' if matches else 'pendiente'
                if d['estado'] == 'duplicado':
                    status = 'duplicada'
                if reasons or errors:
                    status = 'en_revision'
                rows.append({**d, 'estado_carga': status, 'motivos': sorted(set(reasons + errors))})
            if report:
                self.extras(rows, report, book['documentos'])
            for file, sha in hashes.items():
                if digest(self.path(file)) != sha:
                    raise ValueError('un archivo cambió durante la validación, repetí el proceso')
            created = now().isoformat()
            result = {'id': uuid.uuid4().hex, 'fase': 'antes', 'creado_en': created,
                      'motor_sha256': engine_version(),
                      'perfil': book['perfil'], 'huellas': hashes, 'errores': errors, 'facturas': rows,
                      'consulta_marangatu': report['consultado_en'] if report else None,
                      'bandeja': str(folder / 'revision.html')}
            result['apto_para_carga'] = bool(rows) and not errors and not any(r['estado_carga'] == 'en_revision' for r in rows)
            result['para_cargar'] = [r['id'] for r in rows if r['estado_carga'] == 'pendiente'] if result['apto_para_carga'] else []
            return self.persist(folder, 'validacion', result)

    def extras(self, rows, report, expected):
        for i, d in enumerate(report['documentos']):
            if not any(set(identities(d)) & set(identities(e)) for e in expected):
                rows.append({**d, 'id': f'portal-{i + 1}', 'fuentes': [report['fuente']],
                             'estado_carga': 'en_revision', 'motivos': ['factura del portal ausente del libro']})

    def current(self, lot, name='validacion'):
        folder = self.folder(lot)
        result = self.read(folder / f'{name}.json', {})
        if result.get('motor_sha256') != engine_version():
            raise ValueError('cambió el validador, volvé a validar el lote')
        for file, sha in result['huellas'].items():
            if digest(self.path(file)) != sha:
                raise ValueError('cambió un archivo validado, volvé a validar el lote')
        if not result['consulta_marangatu'] or now() - timestamp(result['consulta_marangatu']) > timedelta(hours=24):
            raise ValueError('falta un reporte vigente de Marangatu, volvé a validar')
        return result

    def reconcile(self, lot):
        with LOCK:
            folder = self.folder(lot)
            before = self.current(lot)
            if not before['apto_para_carga']:
                raise ValueError('el lote no pasó la validación previa')
            hashes = dict(before['huellas'])
            hashes[str(folder / 'validacion.json')] = digest(folder / 'validacion.json')
            try:
                report = self.report(folder, 'despues', before['perfil'], hashes, after=before['creado_en'])
            except (ValueError, OSError, KeyError) as e:
                result = {**before, 'id': uuid.uuid4().hex, 'validacion_id': before['id'],
                          'fase': 'despues', 'creado_en': now().isoformat(), 'huellas': hashes,
                          'apto_para_carga': False, 'para_cargar': [], 'conciliado': False,
                          'consulta_marangatu': None, 'errores': [str(e)],
                          'facturas': [{**d, 'estado_carga': 'en_revision', 'motivos': [str(e)]}
                                       for d in before['facturas']]}
                return self.persist(folder, 'conciliacion', result)
            rows = []
            for d in before['facturas']:
                if d['estado_carga'] == 'duplicada':
                    rows.append(d)
                    continue
                matches = [r for r in report['documentos'] if set(identities(d)) & set(identities(r))]
                reasons = []
                if len(matches) != 1:
                    reasons.append('factura faltante en el portal' if not matches else 'factura duplicada en el portal')
                elif fiscal(matches[0]) != fiscal(d):
                    reasons.append('diferencias: ' + ', '.join(k for k in FIELDS if fiscal(matches[0])[k] != fiscal(d)[k]))
                rows.append({**d, 'estado_carga': 'en_revision' if reasons else 'cargada', 'motivos': reasons})
            self.extras(rows, report, before['facturas'])
            result = {'id': uuid.uuid4().hex, 'validacion_id': before['id'], 'fase': 'despues',
                      'motor_sha256': engine_version(),
                      'creado_en': now().isoformat(), 'perfil': before['perfil'], 'huellas': hashes,
                      'consulta_marangatu': report['consultado_en'], 'errores': [], 'facturas': rows,
                      'apto_para_carga': False, 'para_cargar': [], 'bandeja': str(folder / 'revision.html'),
                      'conciliado': not any(r['estado_carga'] == 'en_revision' for r in rows)}
            for file, sha in hashes.items():
                if digest(self.path(file)) != sha:
                    raise ValueError('un archivo cambió durante la conciliación, repetí el proceso')
            return self.persist(folder, 'conciliacion', result)

    def query(self, lot, status=None):
        folder = self.folder(lot)
        name = 'conciliacion' if (folder / 'conciliacion.json').exists() else 'validacion'
        result = self.read(folder / f'{name}.json', {})
        if name == 'conciliacion':
            validation = self.read(folder / 'validacion.json', {})
            if result.get('validacion_id') != validation['id']:
                name, result = 'validacion', validation
        try:
            self.current(lot, name)
            stale = None
        except (ValueError, OSError) as e:
            stale = str(e)
        rows = result['facturas']
        if stale:
            rows = [{**r, 'estado_carga': 'en_revision', 'motivos': sorted(set(r['motivos'] + [stale]))} for r in rows]
        return {'vigente': stale is None, 'consulta_marangatu': result['consulta_marangatu'],
                'origen': 'reporte descargado de Marangatu, no consulta en vivo',
                'fase': result['fase'], 'bandeja': result['bandeja'],
                'apto_para_carga': result['apto_para_carga'] and stale is None,
                'conciliado': result.get('conciliado', False) and stale is None,
                'errores': result['errores'] + ([stale] if stale else []),
                'estados': dict(Counter(r['estado_carga'] for r in rows)),
                'facturas': [r for r in rows if status is None or r['estado_carga'] == status]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('accion', choices=['validar', 'conciliar', 'consultar'])
    parser.add_argument('lote')
    parser.add_argument('--datos', required=True)
    args = parser.parse_args()
    store = Store(args.datos)
    action = {'validar': store.validate, 'conciliar': store.reconcile, 'consultar': store.query}[args.accion]
    print(json.dumps(action(args.lote), ensure_ascii=False, indent=2))
