import json
import os
import sys
import unittest
from pathlib import Path

import test_validacion

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None


@unittest.skipIf(ClientSession is None, 'instalá requirements.txt para probar MCP')
class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_tools_and_validation(self):
        fixture = test_validacion.ValidationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        server = Path(__file__).resolve().parents[3] / 'servidor_mcp.py'
        params = StdioServerParameters(command=sys.executable, args=[str(server)],
                                       env={**os.environ, 'IMPUESTOS_DATOS': str(fixture.root)})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertEqual({t.name for t in tools}, {
                    'validar_lote', 'conciliar_lote', 'obtener_facturas_cargadas',
                    'obtener_facturas_pendientes', 'obtener_facturas_en_revision', 'obtener_resumen_lote'})
                async def call(name, **args):
                    result = await session.call_tool(name, {'lote': 'lote', **args})
                    self.assertFalse(result.isError, result.content)
                    return json.loads(result.content[0].text)
                self.assertTrue((await call('validar_lote'))['apto_para_carga'])
                pending = await call('obtener_facturas_pendientes')
                self.assertEqual(pending['cantidad'], 1)
                self.assertEqual(pending['facturas'][0]['id'], 'f1')
                fixture.report('despues', [fixture.doc])
                self.assertTrue((await call('conciliar_lote'))['conciliado'])
                self.assertEqual((await call('obtener_facturas_cargadas'))['cantidad'], 1)
                self.assertEqual((await call('obtener_facturas_en_revision'))['cantidad'], 0)
                self.assertTrue((await call('obtener_resumen_lote'))['conciliado'])
                bad = await session.call_tool('validar_lote', {'lote': '../outside'})
                self.assertTrue(bad.isError)


if __name__ == '__main__':
    unittest.main()
