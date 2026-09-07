import copy
import tempfile
import unittest
from pathlib import Path

from facturas import CHECKS, build, digest, inventory, safe_cell


class LibroTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        source = Path(self.tmp.name) / 'factura.png'
        source.write_bytes(b'fixture sintetico, no comprobante fiscal')
        self.doc = {
            'id': 'f1', 'fecha': '2026-09-02', 'emisor': 'Proveedor ficticio',
            'ruc_emisor': '80000000-0', 'numero': '001-001-0000001', 'timbrado': '12345678',
            'tipo': 'factura', 'origen': 'preimpreso', 'concepto': 'alimentos de prueba',
            'total_gs': 110000, 'candidato_gs': 110000, 'iva_credito_gs': 10000,
            'otro_impuesto_gs': 0, 'moneda': 'PYG', 'pais': 'PY', 'condicion': 'contado',
            'categoria': 'alimentacion', 'decision': 'deducible',
            'pagos': [{'fecha': '2026-09-02', 'monto_gs': 110000, 'respaldo': 'fixture contado'}],
            'controles': dict.fromkeys(CHECKS, True), 'motivo': 'evidencia sintética',
            'norma_url': 'https://www.dnit.gov.py/en/web/portal-institucional/w/d-ley-n-6380-19',
            'articulo': '64 y 68', 'observaciones': [],
            'fuentes': [{'archivo': str(source), 'sha256': digest(source), 'ubicacion': 'página 1'}]}
        self.data = {'perfil': {'ejercicio': 2026, 'ruc_titular': '1000000-0',
                    'contribuyente_iva': True, 'inicio_deducciones': '2026-09-01',
                    'normativa_verificada': True,
                    'fuentes_vigencia': [{'url': self.doc['norma_url'], 'consulta': '2026-09-07'}]},
                    'documentos': [self.doc]}

    def row(self):
        return build(self.data)['documentos'][0]

    def test_vat_excluded_once(self):
        self.assertEqual(self.row()['deducible_gs'], 100000)

    def test_partial_invoice(self):
        self.doc.update(candidato_gs=55000, iva_credito_gs=5000)
        self.assertEqual(self.row()['deducible_gs'], 50000)

    def test_duplicates(self):
        self.data['documentos'].append({**copy.deepcopy(self.doc), 'id': 'copy'})
        out = build(self.data)
        self.assertEqual(out['resumen']['deducible_identificado_gs'], 100000)
        self.assertEqual(out['documentos'][1]['estado'], 'duplicado')

    def test_conflicting_copies(self):
        self.data['documentos'].append({**copy.deepcopy(self.doc), 'id': 'copy', 'total_gs': 120000})
        self.assertTrue(all(r['estado'] == 'revisar' for r in build(self.data)['documentos']))

    def test_before_threshold_or_wrong_year(self):
        for dt in ['2026-08-31', '2025-09-02', '2027-09-02']:
            with self.subTest(dt=dt):
                self.doc['pagos'][0]['fecha'] = dt
                self.assertIsNone(self.row()['deducible_gs'])

    def test_unknown_profile(self):
        self.data['perfil']['inicio_deducciones'] = None
        self.assertEqual(self.row()['estado'], 'revisar')

    def test_unverified_rules(self):
        self.data['perfil']['normativa_verificada'] = False
        self.assertIsNone(self.row()['deducible_gs'])

    def test_missing_amount_and_bad_math(self):
        for changes in [{'total_gs': None}, {'iva_credito_gs': None},
                        {'candidato_gs': 120000}, {'iva_credito_gs': 120000}]:
            original = copy.deepcopy(self.doc)
            self.doc.update(changes)
            self.assertIsNone(self.row()['deducible_gs'])
            self.doc.clear()
            self.doc.update(original)

    def test_credit_and_special_categories(self):
        for field, value in [('condicion', 'credito'), ('categoria', 'donacion'),
                             ('categoria', 'vivienda'), ('pais', 'AR'), ('moneda', 'USD')]:
            old = self.doc[field]
            self.doc[field] = value
            self.assertEqual(self.row()['estado'], 'revisar')
            self.doc[field] = old

    def test_credit_note_blocks_original(self):
        self.data['documentos'].append({**copy.deepcopy(self.doc), 'id': 'nc',
            'tipo': 'nota_credito', 'factura_asociada': 'f1'})
        self.assertEqual(build(self.data)['resumen']['deducible_identificado_gs'], 0)

    def test_adjustment_of_duplicate_blocks_all_copies(self):
        self.data['documentos'].extend([
            {**copy.deepcopy(self.doc), 'id': 'copy'},
            {**copy.deepcopy(self.doc), 'id': 'nc', 'tipo': 'nota_credito',
             'factura_asociada': 'copy'}])
        self.assertEqual(build(self.data)['resumen']['deducible_identificado_gs'], 0)

    def test_transitive_identity_conflict(self):
        self.doc['cdc'] = '1' * 44
        self.data['documentos'].extend([
            {**copy.deepcopy(self.doc), 'id': 'copy', 'cdc': None},
            {**copy.deepcopy(self.doc), 'id': 'copy2', 'timbrado': None, 'total_gs': 120000}])
        self.assertTrue(all(r['estado'] == 'revisar' for r in build(self.data)['documentos']))

    def test_electronic_registered_still_in_book(self):
        self.doc.update(origen='electronico', ya_registrado=True)
        self.assertEqual(self.row()['ruta_carga'], 'ya registrado')
        self.assertEqual(self.row()['deducible_gs'], 100000)
        self.doc['ya_registrado'] = False
        self.assertEqual(self.row()['ruta_carga'], 'recuperar en Marangatu')

    def test_original_changed(self):
        Path(self.doc['fuentes'][0]['archivo']).write_bytes(b'changed')
        self.assertEqual(self.row()['estado'], 'revisar')

    def test_inventory_and_injection(self):
        self.assertEqual(len(inventory(self.tmp.name)['archivos']), 1)
        self.assertEqual(safe_cell('  =HYPERLINK("bad")'), "'  =HYPERLINK(\"bad\")")
        self.assertEqual(safe_cell(200), 200)

    def test_duplicate_ids_rejected(self):
        self.data['documentos'].append(copy.deepcopy(self.doc))
        with self.assertRaises(ValueError):
            build(self.data)


if __name__ == '__main__':
    unittest.main()
