"""Consultá lotes y reportes locales por MCP, sin enviar datos a Marangatu."""
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

sys.path.insert(0, str(Path(__file__).resolve().parent / 'skills/facturas-irp-paraguay/scripts'))
from validacion import Store

mcp = FastMCP('impuestos-paraguay')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def store():
    root = os.environ.get('IMPUESTOS_DATOS')
    if not root:
        raise ValueError('configurá IMPUESTOS_DATOS con el directorio privado de lotes')
    return Store(root)


@mcp.tool(annotations=WRITE)
def validar_lote(lote: str) -> dict:
    """Validá extracción, XLSX y reporte previo, y generá la bandeja de revisión."""
    result = store().validate(lote)
    return {k: result[k] for k in ('id', 'apto_para_carga', 'para_cargar', 'errores', 'bandeja')}


@mcp.tool(annotations=WRITE)
def conciliar_lote(lote: str) -> dict:
    """Compará con un reporte nuevo de Marangatu después de cargar, sin enviar datos."""
    result = store().reconcile(lote)
    return {k: result[k] for k in ('id', 'conciliado', 'errores', 'bandeja')}


def page(lote, status, desde, limite):
    if not 1 <= limite <= 200 or desde < 0:
        raise ValueError('usá desde >= 0 y un límite entre 1 y 200')
    result = store().query(lote, status)
    result['cantidad'] = len(result['facturas'])
    result['facturas'] = result['facturas'][desde:desde + limite]
    return result


@mcp.tool(annotations=READ)
def obtener_facturas_cargadas(lote: str, desde: int = 0, limite: int = 50) -> dict:
    """Consultá facturas coincidentes con el último reporte validado, incluye fecha de consulta."""
    return page(lote, 'cargada', desde, limite)


@mcp.tool(annotations=READ)
def obtener_facturas_pendientes(lote: str, desde: int = 0, limite: int = 50) -> dict:
    """Consultá facturas ausentes del reporte previo, antes de su carga."""
    return page(lote, 'pendiente', desde, limite)


@mcp.tool(annotations=READ)
def obtener_facturas_en_revision(lote: str, desde: int = 0, limite: int = 50) -> dict:
    """Consultá dudas y diferencias, con el motivo y los archivos de respaldo."""
    return page(lote, 'en_revision', desde, limite)


@mcp.tool(annotations=READ)
def obtener_resumen_lote(lote: str) -> dict:
    """Consultá estados, vigencia de la validación y ubicación de la bandeja humana."""
    result = store().query(lote)
    result.pop('facturas')
    return result


if __name__ == '__main__':
    mcp.run(transport='stdio')
