"""
╔══════════════════════════════════════════════════════════════╗
║  servidor.py — AutoTaller WhatsApp Bot                      ║
║  Soporta mensajes de texto Y notas de voz (Whisper)         ║
╚══════════════════════════════════════════════════════════════╝
"""

import groq
import os
import requests
import tempfile
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy import create_engine, text
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
import groq

load_dotenv()

app         = FastAPI(title="AutoTaller WhatsApp Bot")
engine      = create_engine(os.getenv("DATABASE_URL"), echo=False)


# Credenciales de Twilio para descargar audios
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")

# Memoria por usuario
historiales = {}


# ──────────────────────────────────────────────────────────────────
# FUNCIÓN: TRANSCRIBIR AUDIO CON WHISPER
# ──────────────────────────────────────────────────────────────────

def transcribir_audio(media_url: str) -> str:
    try:
        respuesta = requests.get(
            media_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=30
        )
        if respuesta.status_code != 200:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as archivo_temp:
            archivo_temp.write(respuesta.content)
            ruta_temp = archivo_temp.name

        # Usar Groq Whisper en lugar de OpenAI
        groq_client = groq.Groq(api_key=os.getenv("GROQ_API_KEY"))
        with open(ruta_temp, "rb") as archivo_audio:
            transcripcion = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=archivo_audio,
                language="es"
            )

        os.unlink(ruta_temp)
        return transcripcion.text

    except Exception as e:
        print(f"Error transcribiendo audio: {e}")
        return ""

# ──────────────────────────────────────────────────────────────────
# FUNCIÓN AUXILIAR BD
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
        precio = f"${int(f['precio_venta']):,}".replace(",", ".")
        icono  = "❌" if f["disponibilidad"] == "AGOTADO" else "⚠️" if f["disponibilidad"] == "STOCK BAJO" else "✅"
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
    Usar cuando el cliente mencione la marca o modelo de su vehículo.
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
        precio = f"${int(f['precio_venta']):,}".replace(",", ".")
        icono  = "❌" if f["disponibilidad"] == "AGOTADO" else "✅"
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

    f       = filas[0]
    p_venta = f"${int(f['precio_venta']):,}".replace(",", ".")
    icono   = "❌" if f["disponibilidad"] == "AGOTADO" else "⚠️" if f["disponibilidad"] == "STOCK BAJO" else "✅"

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
    Lista repuestos agotados o con stock bajo.
    Usar cuando pregunten qué falta, qué hay que pedir o alertas de inventario.
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
        icono = "❌" if f["estado"] == "AGOTADO" else "⚠️"
        respuesta += f"{icono} *{f['nombre']}*\n"
        respuesta += f"   Stock: {f['stock_actual']}/{f['stock_minimo']} {f['unidad']}\n\n"
    return respuesta


# ──────────────────────────────────────────────────────────────────
# ENSAMBLAJE DEL AGENTE
# ──────────────────────────────────────────────────────────────────

tools = [
    consultar_repuestos,
    consultar_compatibilidad,
    consultar_precio_repuesto,
    repuestos_agotados_o_bajos,
]

llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

agente = create_react_agent(
    model=llm,
    tools=tools,
    prompt="""Eres el asistente de AutoTaller, un taller mecánico colombiano.
Ayudas a clientes y técnicos a consultar repuestos automotrices.
Responde en español, de forma breve y clara (es WhatsApp).

REGLAS IMPORTANTES — SIEMPRE sigue estas reglas antes de responder:
- Si el mensaje menciona una marca (Toyota, Chevrolet, Renault, Mazda, 
  Hyundai, Kia, Nissan, Ford) → usar consultar_compatibilidad
- Si menciona tipo de repuesto (filtro, pastillas, batería, amortiguador, 
  frenos, aceite, bujía, correa) → usar consultar_repuestos
- Si menciona un código (MOT-001, FRE-003, etc.) → usar consultar_precio_repuesto
- Si pregunta qué falta, qué está agotado o qué hay que pedir → usar repuestos_agotados_o_bajos
- NUNCA respondas sin consultar primero una tool
- NUNCA preguntes "¿necesitas algo más?" sin haber dado información primero

Ejemplos:
- "repuestos para Toyota" → consultar_compatibilidad(marca="Toyota")
- "qué tienen para un Spark" → consultar_compatibilidad(marca="Chevrolet", modelo="Spark")
- "precio del filtro de aceite" → consultar_repuestos(nombre="filtro de aceite")
- "qué está agotado" → repuestos_agotados_o_bajos()"""
)


# ──────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────

@app.get("/")
def raiz():
    return {"status": "ok", "servicio": "AutoTaller WhatsApp Bot con voz"}


@app.post("/webhook")
async def webhook(
    From:           str = Form(...),
    Body:           str = Form(default=""),
    NumMedia:       str = Form(default="0"),
    MediaUrl0:      str = Form(default=""),
    MediaContentType0: str = Form(default=""),
):
    """
    Recibe mensajes de WhatsApp via Twilio.
    Soporta texto y notas de voz (audio/ogg).
    
    Twilio envía:
      From      → número del usuario
      Body      → texto del mensaje (vacío si es audio)
      NumMedia  → cantidad de archivos adjuntos
      MediaUrl0 → URL del primer archivo adjunto
      MediaContentType0 → tipo de archivo (audio/ogg para notas de voz)
    """
    numero  = From.replace("whatsapp:", "")
    mensaje = Body.strip()

    # ── Detectar si es una nota de voz ───────────────────────────
    es_audio = (
        int(NumMedia) > 0 and
        MediaUrl0 and
        "audio" in MediaContentType0
    )

    if es_audio:
        print(f"🎤 Audio recibido de {numero}, transcribiendo...")
        mensaje = transcribir_audio(MediaUrl0)
        print(f"📝 Transcripción: {mensaje}")

        if not mensaje:
            twiml = MessagingResponse()
            twiml.message("Lo siento, no pude entender el audio. ¿Puedes escribir tu consulta?")
            return PlainTextResponse(str(twiml), media_type="application/xml")

    # Si no hay texto ni audio válido
    if not mensaje:
        twiml = MessagingResponse()
        twiml.message("Hola 👋 Soy el asistente de AutoTaller. ¿En qué te puedo ayudar?")
        return PlainTextResponse(str(twiml), media_type="application/xml")

    # ── Procesar con el agente ────────────────────────────────────
    if numero not in historiales:
        historiales[numero] = []

    historial = historiales[numero]
    historial.append({"role": "user", "content": mensaje})

    try:
        resultado = agente.invoke({"messages": historial})
        respuesta = resultado["messages"][-1].content
    except Exception as e:
        respuesta = "Lo siento, ocurrió un error. Intenta de nuevo."
        print(f"Error agente: {e}")

    historial.append({"role": "assistant", "content": respuesta})

    # Limitar historial a 20 mensajes
    if len(historial) > 20:
        historiales[numero] = historial[-20:]

    # Indicar si el mensaje fue por voz
    if es_audio:
        respuesta = f"🎤 _Escuché: \"{mensaje}\"_\n\n{respuesta}"

    twiml = MessagingResponse()
    twiml.message(respuesta)
    return PlainTextResponse(str(twiml), media_type="application/xml")