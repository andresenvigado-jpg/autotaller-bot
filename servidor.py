"""
╔══════════════════════════════════════════════════════════════╗
║  servidor.py                                                 ║
║  Servidor FastAPI que recibe mensajes de WhatsApp            ║
║  via Twilio y los procesa con el agente de repuestos.        ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy import create_engine, text
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent

load_dotenv()

app    = FastAPI(title="AutoTaller WhatsApp Bot")
engine = create_engine(os.getenv("DATABASE_URL"), echo=False)

# ── Memoria por usuario ───────────────────────────────────────────
# Guarda el historial de conversación de cada número de WhatsApp
# { "+573001234567": [ {role, content}, ... ] }
historiales = {}


# ──────────────────────────────────────────────────────────────────
# FUNCIÓN AUXILIAR
# ──────────────────────────────────────────────────────────────────

def ejecutar_query(sql: str) -> list:
    with engine.connect() as conn:
        resultado = conn.execute(text(sql))
        columnas  = resultado.keys()
        return [dict(zip(columnas, fila)) for fila in resultado.fetchall()]


# ──────────────────────────────────────────────────────────────────
# TOOLS
# ──────────────────────────────────────────────────────────────────

@tool
def consultar_repuestos(categoria: str = "", nombre: str = "") -> str:
    """
    Consulta repuestos disponibles en el taller por categoría o nombre.
    Categorías: Motor, Frenos, Suspensión, Eléctrico, Transmisión, Refrigeración, Dirección.
    Muestra precio, stock y disponibilidad.
    """
    condiciones = ["r.activo = 'SI'"]
    if categoria:
        condiciones.append(f"r.categoria ILIKE '%{categoria}%'")
    if nombre:
        condiciones.append(f"r.nombre ILIKE '%{nombre}%'")

    sql = f"""
        SELECT r.codigo, r.nombre, r.categoria, r.precio_venta,
               r.stock_actual, r.unidad,
               CASE WHEN r.stock_actual = 0 THEN 'AGOTADO'
                    WHEN r.stock_actual <= r.stock_minimo THEN 'STOCK BAJO'
                    ELSE 'DISPONIBLE' END AS disponibilidad
        FROM repuestos r
        WHERE {" AND ".join(condiciones)}
        ORDER BY r.categoria, r.nombre
        LIMIT 10
    """
    filas = ejecutar_query(sql)
    if not filas:
        return "No encontré repuestos con ese criterio."

    respuesta = f"🔩 *{len(filas)} repuesto(s) encontrado(s):*\n\n"
    for f in filas:
        precio    = f"${int(f['precio_venta']):,}".replace(",", ".")
        icono     = "❌" if f["disponibilidad"] == "AGOTADO" else "⚠️" if f["disponibilidad"] == "STOCK BAJO" else "✅"
        respuesta += f"{icono} *{f['nombre']}*\n"
        respuesta += f"   Código: {f['codigo']}\n"
        respuesta += f"   Precio: {precio} COP\n"
        respuesta += f"   Stock: {f['stock_actual']} {f['unidad']}\n\n"
    return respuesta


@tool
def consultar_compatibilidad(marca: str, modelo: str = "") -> str:
    """
    Consulta qué repuestos son compatibles con una marca y modelo de vehículo.
    Marcas disponibles: Toyota, Chevrolet, Renault, Mazda, Hyundai, Kia, Nissan, Ford.
    """
    filtro_modelo = f"AND rm.modelos ILIKE '%{modelo}%'" if modelo else ""
    sql = f"""
        SELECT r.codigo, r.nombre, r.categoria, r.precio_venta,
               r.stock_actual, r.unidad,
               CASE WHEN r.stock_actual = 0 THEN 'AGOTADO'
                    WHEN r.stock_actual <= r.stock_minimo THEN 'STOCK BAJO'
                    ELSE 'DISPONIBLE' END AS disponibilidad
        FROM repuestos r
        JOIN repuesto_marca rm ON rm.id_repuesto = r.id
        JOIN marcas m ON m.id = rm.id_marca
        WHERE m.nombre ILIKE '%{marca}%'
          AND r.activo = 'SI' {filtro_modelo}
        ORDER BY r.categoria, r.nombre
        LIMIT 10
    """
    filas = ejecutar_query(sql)
    if not filas:
        return f"No encontré repuestos para {marca} {modelo}."

    respuesta = f"🚗 *Repuestos para {marca} {modelo}:*\n\n"
    for f in filas:
        precio    = f"${int(f['precio_venta']):,}".replace(",", ".")
        icono     = "❌" if f["disponibilidad"] == "AGOTADO" else "✅"
        respuesta += f"{icono} *{f['nombre']}*\n"
        respuesta += f"   Precio: {precio} COP | Stock: {f['stock_actual']} {f['unidad']}\n\n"
    return respuesta


@tool
def consultar_precio_repuesto(codigo: str) -> str:
    """
    Consulta precio detallado y disponibilidad de un repuesto por su código.
    Ejemplo de códigos: MOT-001, FRE-003, ELE-001, SUS-002.
    """
    sql = f"""
        SELECT r.codigo, r.nombre, r.descripcion, r.precio_compra,
               r.precio_venta, r.stock_actual, r.stock_minimo, r.unidad,
               p.nombre AS proveedor, p.dias_entrega,
               CASE WHEN r.stock_actual = 0 THEN 'AGOTADO'
                    WHEN r.stock_actual <= r.stock_minimo THEN 'STOCK BAJO'
                    ELSE 'DISPONIBLE' END AS disponibilidad
        FROM repuestos r
        JOIN proveedores p ON p.id = r.id_proveedor
        WHERE r.codigo ILIKE '{codigo}'
    """
    filas = ejecutar_query(sql)
    if not filas:
        return f"No encontré el repuesto con código '{codigo}'."

    f         = filas[0]
    p_venta   = f"${int(f['precio_venta']):,}".replace(",", ".")
    icono     = "❌" if f["disponibilidad"] == "AGOTADO" else "⚠️" if f["disponibilidad"] == "STOCK BAJO" else "✅"

    return (
        f"🔩 *{f['nombre']}*\n"
        f"Código: {f['codigo']}\n"
        f"Descripción: {f['descripcion']}\n"
        f"💰 Precio: *{p_venta} COP* / {f['unidad']}\n"
        f"📦 Stock: {f['stock_actual']} {f['unidad']} {icono}\n"
        f"🏭 Proveedor: {f['proveedor']}\n"
        f"🚚 Entrega: {f['dias_entrega']} días hábiles"
    )


@tool
def repuestos_agotados_o_bajos() -> str:
    """
    Lista repuestos agotados o con stock bajo. Útil para alertas de inventario.
    No requiere parámetros.
    """
    sql = """
        SELECT r.codigo, r.nombre, r.stock_actual, r.stock_minimo, r.unidad,
               CASE WHEN r.stock_actual = 0 THEN 'AGOTADO' ELSE 'STOCK BAJO' END AS estado
        FROM repuestos r
        WHERE r.stock_actual <= r.stock_minimo AND r.activo = 'SI'
        ORDER BY r.stock_actual ASC
    """
    filas = ejecutar_query(sql)
    if not filas:
        return "✅ Todo el inventario está en niveles correctos."

    respuesta = f"⚠️ *{len(filas)} repuesto(s) requieren atención:*\n\n"
    for f in filas:
        icono     = "❌" if f["estado"] == "AGOTADO" else "⚠️"
        respuesta += f"{icono} *{f['nombre']}*\n"
        respuesta += f"   Stock: {f['stock_actual']}/{f['stock_minimo']} {f['unidad']}\n\n"
    return respuesta


# ──────────────────────────────────────────────────────────────────
# AGENTE
# ──────────────────────────────────────────────────────────────────

tools = [
    consultar_repuestos,
    consultar_compatibilidad,
    consultar_precio_repuesto,
    repuestos_agotados_o_bajos,
]

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

agente = create_react_agent(
    model=llm,
    tools=tools,
    prompt="""Eres el asistente de AutoTaller por WhatsApp.
Ayudas a clientes y técnicos a consultar repuestos automotrices.
Responde en español, de forma breve y clara (es WhatsApp, no un informe).
Usa emojis moderadamente. Máximo 3-4 líneas por respuesta cuando sea posible.
Si el cliente menciona marca de vehículo usa consultar_compatibilidad.
Si pregunta por código específico usa consultar_precio_repuesto."""
)


# ──────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────

@app.get("/")
def raiz():
    """Endpoint de verificación — Railway lo usa para saber si el servidor está vivo."""
    return {"status": "ok", "servicio": "AutoTaller WhatsApp Bot"}


@app.post("/webhook")
async def webhook(
    From: str = Form(...),       # Número del usuario: "whatsapp:+573001234567"
    Body: str = Form(...),       # Texto del mensaje de WhatsApp
):
    """
    Twilio llama este endpoint cada vez que llega un mensaje de WhatsApp.
    Procesa el mensaje con el agente y responde en formato TwiML.
    """
    numero   = From.replace("whatsapp:", "")  # Limpiamos el prefijo
    mensaje  = Body.strip()

    # Recuperar o iniciar historial de este usuario
    if numero not in historiales:
        historiales[numero] = []

    historial = historiales[numero]
    historial.append({"role": "user", "content": mensaje})

    # Invocar el agente
    try:
        resultado = agente.invoke({"messages": historial})
        respuesta = resultado["messages"][-1].content
    except Exception as e:
        respuesta = "Lo siento, ocurrió un error procesando tu consulta. Intenta de nuevo."
        print(f"Error agente: {e}")

    # Guardar respuesta en historial
    historial.append({"role": "assistant", "content": respuesta})

    # Limitar historial a los últimos 10 intercambios (20 mensajes)
    if len(historial) > 20:
        historiales[numero] = historial[-20:]

    # Responder a Twilio en formato TwiML
    twiml    = MessagingResponse()
    twiml.message(respuesta)
    return PlainTextResponse(str(twiml), media_type="application/xml")
