import csv
import html
import json
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from facturas import build, digest
import test_facturas
from validacion import FIELDS, HEADERS, Store, fiscal


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def xml_sheet(cells):
    rows = {}
    for addr, value in cells.items():
        n = ''.join(c for c in addr if c.isdigit())
        if isinstance(value, tuple):
            cell = f'<c r="{addr}"><f>{html.escape(value[0])}</f><v>{value[1]}</v></c>'
        elif value is None:
            cell = f'<c r="{addr}"/>'
        elif isinstance(value, (int, float)):
            cell = f'<c r="{addr}"><v>{value}</v></c>'
        else:
            cell = f'<c r="{addr}" t="inlineStr"><is><t>{html.escape(value)}</t></is></c>'
        rows.setdefault(n, []).append(cell)
    return ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + ''.join(f'<row r="{n}">{"".join(c)}</row>' for n, c in rows.items()) + '</sheetData></worksheet>')


def workbook(path, data, edits=None):
    book = build(data)
    cells = {f'{chr(65+i)}5': h for i, h in enumerate(HEADERS)}
    loads = {f'{chr(65+i)}1': h for i, h in enumerate(('id', *FIELDS))}
    for n, d in enumerate(book['documentos'], 6):
        dt = datetime.fromisoformat(d['fecha'])
        row = [d['id'], (dt - datetime(1899, 12, 30)).days + .5, d['emisor'], d['numero'],
               d['concepto'], d['total_gs'], d['deducible_gs'], d['estado'],
               ' · '.join([d['motivo'], *d['pendientes']]), d['ruta_carga'],
               ' · '.join(f"{s['archivo']} {s['ubicacion']}" for s in d['fuentes']),
               d['articulo'] + ' ' + d['norma_url']]
        cells.update({f'{chr(65+i)}{n}': v for i, v in enumerate(row)})
        record = fiscal(d)
        record['imputaciones'] = ','.join(record['imputaciones'])
        load = [d['id'], *(record[k] for k in FIELDS)]
        loads.update({f'{chr(65+i)}{n-4}': v for i, v in enumerate(load)})
    sheets = {'Facturas': cells, 'Carga': loads, 'Resumen': {
        'B5': (f'SUM(Facturas!G6:G{max(6, len(book["documentos"])+5)})', book['resumen']['deducible_identificado_gs'])}}
    for name, changes in (edits or {}).items():
        sheets[name].update(changes)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml',
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + ''.join(f'<sheet name="{name}" sheetId="{i}" r:id="r{i}"/>' for i, name in enumerate(sheets, 1))
            + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships>' + ''.join(
            f'<Relationship Id="r{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, 4)) + '</Relationships>')
        for i, cells in enumerate(sheets.values(), 1):
            z.writestr(f'xl/worksheets/sheet{i}.xml', xml_sheet(cells))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_facturas.LibroTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = Path(self.fixture.tmp.name)
        self.folder = self.root / 'lote'
        self.folder.mkdir()
        self.store = Store(self.root)
        self.data = self.fixture.data
        self.data['perfil']['contribuyente_iva'] = False
        self.doc = self.data['documentos'][0]
        self.doc.update(ruc_destinatario='1000000-0', gravado_10_gs=110000,
                        gravado_5_gs=0, exento_gs=0, iva_credito_gs=0,
                        imputaciones=['IRP'], cotejo_original={'verificado': True, 'evidencia': 'segunda lectura ficticia'})
        self.inputs()
        self.report('antes', [])

    def inputs(self, edits=None):
        put(self.folder / 'extraccion.json', self.data)
        put(self.folder / 'inventario.json', {'archivos': self.doc['fuentes'], 'omitidos': []})
        workbook(self.folder / 'facturas-irp.xlsx', self.data, edits)

    def report(self, phase, documents, **changes):
        rows = [{**fiscal(d), 'referencia_original': f'fila {i}', 'estado_registro': 'registrado'}
                for i, d in enumerate(documents, 2)]
        source = self.folder / f'portal-{phase}.csv'
        with source.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[*FIELDS, 'referencia_original', 'estado_registro'])
            writer.writeheader()
            writer.writerows(rows)
        value = {'ruc_titular': self.data['perfil']['ruc_titular'], 'ejercicio': 2026,
                 'consultado_en': datetime.now(timezone.utc).isoformat(),
                 'completo': True, 'cotejado_con_original': True,
                 'fuente': {'archivo': str(source), 'sha256': digest(source)},
                 'cantidad': len(rows), 'total_gs': sum(r['total_gs'] for r in rows), 'documentos': rows, **changes}
        put(self.folder / f'marangatu-{phase}.json', value)
        return value

    def test_complete_flow(self):
        result = self.store.validate('lote')
        self.assertTrue(result['apto_para_carga'])
        self.assertEqual(result['para_cargar'], ['f1'])
        self.report('despues', [self.doc])
        after = self.store.reconcile('lote')
        self.assertTrue(after['conciliado'])
        self.assertEqual(len(self.store.query('lote', 'cargada')['facturas']), 1)
        self.assertTrue((self.folder / 'revision.html').is_file())
        self.assertEqual(len(list((self.folder / 'historial').glob('*.json'))), 2)

    def test_existing_invoice_not_sent_again(self):
        self.report('antes', [self.doc])
        result = self.store.validate('lote')
        self.assertTrue(result['apto_para_carga'])
        self.assertEqual(result['para_cargar'], [])
        self.assertEqual(result['facturas'][0]['estado_carga'], 'cargada')

    def test_edited_cell_blocks_even_with_same_total(self):
        for changes in [{'Facturas': {'D6': '001-001-0000009'}},
                        {'Carga': {'B2': '9999999-0'}},
                        {'Resumen': {'B5': ('110000', 110000)}},
                        {'Facturas': {'F6': ('110000', 110000)}}]:
            with self.subTest(changes=changes):
                self.inputs(changes)
                self.assertFalse(self.store.validate('lote')['apto_para_carga'])

    def test_missing_row_or_added_row(self):
        for edit in [{'A6': None}, {'A7': 'extra'}]:
            self.inputs({'Facturas': edit})
            self.assertFalse(self.store.validate('lote')['apto_para_carga'])

    def test_uncertainty_goes_to_review(self):
        self.doc['cotejo_original']['verificado'] = False
        self.inputs()
        result = self.store.validate('lote')
        self.assertFalse(result['apto_para_carga'])
        self.assertEqual(result['para_cargar'], [])
        self.assertEqual(self.store.query('lote', 'en_revision')['facturas'][0]['id'], 'f1')

    def test_unprocessed_original_blocks(self):
        extra = self.root / 'extra.png'
        extra.write_bytes(b'otro original ficticio')
        put(self.folder / 'inventario.json', {'archivos': [*self.doc['fuentes'],
            {'archivo': str(extra), 'sha256': digest(extra)}], 'omitidos': []})
        self.assertFalse(self.store.validate('lote')['apto_para_carga'])

    def test_local_duplicates_with_different_recipients_block(self):
        self.data['documentos'].append({**self.doc, 'id': 'copy', 'ruc_destinatario': '9999999-0'})
        self.inputs()
        self.assertFalse(self.store.validate('lote')['apto_para_carga'])

    def test_changed_inputs_invalidate_ready_status(self):
        self.store.validate('lote')
        self.doc['total_gs'] += 1
        put(self.folder / 'extraccion.json', self.data)
        query = self.store.query('lote')
        self.assertFalse(query['vigente'])
        self.assertEqual(query['facturas'][0]['estado_carga'], 'en_revision')
        with self.assertRaises(ValueError):
            self.store.reconcile('lote')

    def test_changed_source_invalidate_ready_status(self):
        self.store.validate('lote')
        Path(self.doc['fuentes'][0]['archivo']).write_bytes(b'changed')
        self.assertFalse(self.store.query('lote')['vigente'])

    def test_invalid_report_blocks(self):
        for changes in [{'completo': False}, {'ruc_titular': 'other'}, {'cantidad': 9},
                        {'cotejado_con_original': False}, {'total_gs': 12},
                        {'consultado_en': (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}]:
            self.report('antes', [], **changes)
            self.assertFalse(self.store.validate('lote')['apto_para_carga'])

    def test_missing_after_report_does_not_keep_ready_status(self):
        self.store.validate('lote')
        after = self.store.reconcile('lote')
        self.assertFalse(after['conciliado'])
        self.assertFalse(self.store.query('lote')['apto_para_carga'])

    def test_after_must_be_new(self):
        self.store.validate('lote')
        self.report('despues', [self.doc], consultado_en=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())
        self.assertFalse(self.store.reconcile('lote')['conciliado'])

    def test_missing_duplicate_and_extra_portal_rows(self):
        for docs in [[], [self.doc, self.doc], [self.doc, {**self.doc, 'numero': '001-001-0000009'}]]:
            self.report('antes', [])
            self.store.validate('lote')
            self.report('despues', docs)
            self.assertFalse(self.store.reconcile('lote')['conciliado'])
            self.assertTrue(self.store.query('lote', 'en_revision')['facturas'])

    def test_each_fiscal_field_is_reconciled(self):
        for field, value in [('ruc_destinatario', '9999999-0'), ('fecha', '2026-09-03'),
                             ('imputaciones', ['IVA']), ('gravado_10_gs', 100000)]:
            with self.subTest(field=field):
                self.report('antes', [])
                self.store.validate('lote')
                changed = {**self.doc, field: value}
                if field == 'gravado_10_gs':
                    changed['exento_gs'] = 10000
                self.report('despues', [changed])
                self.assertFalse(self.store.reconcile('lote')['conciliado'])

    def test_new_validation_replaces_old_reconciliation(self):
        self.store.validate('lote')
        self.store.reconcile('lote')
        self.report('antes', [])
        self.store.validate('lote')
        self.assertTrue(self.store.query('lote')['apto_para_carga'])

    def test_retry_needs_new_before_report(self):
        self.store.validate('lote')
        self.store.reconcile('lote')
        self.assertFalse(self.store.validate('lote')['apto_para_carga'])

    def test_paths_stay_in_data_directory(self):
        for value in ['../other', '/tmp/other', 'a/b']:
            with self.assertRaises(ValueError):
                self.store.folder(value)
        with self.assertRaises(ValueError):
            self.store.path(self.root.parent / 'secret')
        (self.root / 'escape').symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.store.folder('escape')

    def test_review_html_escapes_invoice_text(self):
        self.doc['observaciones'] = ['<script>alert(1)</script>']
        self.inputs()
        self.store.validate('lote')
        body = (self.folder / 'revision.html').read_text()
        self.assertNotIn('<script>', body)
        self.assertIn('&lt;script&gt;', body)


if __name__ == '__main__':
    unittest.main()
