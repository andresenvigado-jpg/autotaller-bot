"""
╔══════════════════════════════════════════════════════════════╗
║  MÓDULO 1 — agente_repuestos.py                             ║
║  Agente conversacional para consultar disponibilidad        ║
║  y precios de repuestos en un taller automotriz.            ║
║  Ejecutar: python agente_repuestos.py                       ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"), echo=False)


# ──────────────────────────────────────────────────────────────────
# FUNCIÓN AUXILIAR
# ──────────────────────────────────────────────────────────────────

def ejecutar_query(sql: str) -> list:
    """Ejecuta una query SQL y retorna lista de diccionarios."""
    with engine.connect() as conn:
        resultado = conn.execute(text(sql))
        columnas  = resultado.keys()
        return [dict(zip(columnas, fila)) for fila in resultado.fetchall()]


# ──────────────────────────────────────────────────────────────────
# TOOLS DEL AGENTE
# ──────────────────────────────────────────────────────────────────

@tool
def consultar_repuestos(categoria: str = "", nombre: str = "") -> str:
    """
    Consulta el catálogo de repuestos disponibles en el taller.
    Muestra código, nombre, precio de venta, stock actual y si hay disponibilidad.

    Cuándo usar esta tool:
    - El cliente pregunta por un repuesto específico
    - Quiere ver todos los repuestos de una categoría
    - Consulta precios de autopartes
    - Pregunta si tenemos algún repuesto en stock

    Parámetros:
      categoria: filtra por categoría. Valores: 'Motor', 'Frenos', 'Suspensión',
                 'Eléctrico', 'Transmisión', 'Refrigeración', 'Dirección'.
                 Vacío = todas las categorías.
      nombre:    busca por palabra clave en el nombre del repuesto.
                 Ejemplo: 'filtro', 'pastillas', 'batería'. Vacío = todos.

    Ejemplos de preguntas que activan esta tool:
    - "¿Tienen pastillas de freno?"
    - "¿Cuánto vale un filtro de aceite?"
    - "¿Qué repuestos de motor tienen disponibles?"
    - "¿Tienen baterías en stock?"
    """
    condiciones = ["r.activo = 'SI'"]
    if categoria:
        condiciones.append(f"r.categoria ILIKE '%{categoria}%'")
    if nombre:
        condiciones.append(f"r.nombre ILIKE '%{nombre}%'")

    where = "WHERE " + " AND ".join(condiciones)

    sql = f"""
        SELECT
            r.codigo,
            r.nombre,
            r.categoria,
            r.precio_venta,
            r.stock_actual,
            r.stock_minimo,
            r.unidad,
            CASE
                WHEN r.stock_actual = 0        THEN 'AGOTADO'
                WHEN r.stock_actual <= r.stock_minimo THEN 'STOCK BAJO'
                ELSE 'DISPONIBLE'
            END AS disponibilidad
        FROM repuestos r
        {where}
        ORDER BY r.categoria, r.nombre
    """
    filas = ejecutar_query(sql)

    if not filas:
        return "No encontré repuestos con ese criterio de búsqueda."

    respuesta  = f"REPUESTOS ENCONTRADOS — {len(filas)} ítem(s)\n"
    respuesta += "─" * 58 + "\n"

    for f in filas:
        precio     = f"${int(f['precio_venta']):,}".replace(",", ".")
        alerta     = "  ⚠ ¡PEDIR!" if f["disponibilidad"] == "STOCK BAJO" else ""
        no_hay     = "  ❌" if f["disponibilidad"] == "AGOTADO" else ""
        respuesta += (
            f"[{f['codigo']}] {f['nombre']}\n"
            f"  Categoría:     {f['categoria']}\n"
            f"  Precio venta:  {precio} COP / {f['unidad']}\n"
            f"  Stock:         {f['stock_actual']} {f['unidad']} "
            f"— {f['disponibilidad']}{alerta}{no_hay}\n"
        )
    return respuesta


@tool
def consultar_compatibilidad(marca: str, modelo: str = "") -> str:
    """
    Consulta qué repuestos son compatibles con una marca y modelo de vehículo.
    Muy útil cuando el cliente llega con su carro y quiere saber qué piezas le sirven.

    Cuándo usar esta tool:
    - El cliente menciona la marca o modelo de su vehículo
    - Pregunta si un repuesto le sirve a su carro
    - Quiere ver las opciones disponibles para su vehículo

    Parámetros:
      marca:  marca del vehículo. Ejemplos: 'Toyota', 'Chevrolet', 'Renault', 'Mazda',
              'Hyundai', 'Kia', 'Nissan', 'Ford'. (Obligatorio)
      modelo: modelo específico. Ejemplo: 'Corolla', 'Spark', 'Logan'. (Opcional)

    Ejemplos de preguntas:
    - "¿Qué repuestos tienen para Toyota?"
    - "¿Tienen pastillas para un Chevrolet Spark?"
    - "¿Qué filtros sirven para Renault Logan?"
    """
    sql = f"""
        SELECT
            r.codigo,
            r.nombre,
            r.categoria,
            r.precio_venta,
            r.stock_actual,
            r.unidad,
            rm.modelos           AS modelos_compatibles,
            CASE
                WHEN r.stock_actual = 0 THEN 'AGOTADO'
                WHEN r.stock_actual <= r.stock_minimo THEN 'STOCK BAJO'
                ELSE 'DISPONIBLE'
            END AS disponibilidad
        FROM repuestos r
        JOIN repuesto_marca rm ON rm.id_repuesto = r.id
        JOIN marcas m          ON m.id = rm.id_marca
        WHERE m.nombre ILIKE '%{marca}%'
          AND r.activo = 'SI'
          {'AND rm.modelos ILIKE ' + chr(39) + '%' + modelo + '%' + chr(39) if modelo else ''}
        ORDER BY r.categoria, r.nombre
    """
    filas = ejecutar_query(sql)

    if not filas:
        return f"No encontré repuestos compatibles con {marca} {modelo}."

    respuesta  = f"REPUESTOS COMPATIBLES CON {marca.upper()} {modelo.upper()}\n"
    respuesta += f"Total encontrados: {len(filas)}\n"
    respuesta += "─" * 58 + "\n"

    categoria_actual = ""
    for f in filas:
        if f["categoria"] != categoria_actual:
            categoria_actual = f["categoria"]
            respuesta += f"\n▸ {categoria_actual}\n"

        precio = f"${int(f['precio_venta']):,}".replace(",", ".")
        respuesta += (
            f"  [{f['codigo']}] {f['nombre']}\n"
            f"  Precio: {precio} COP / {f['unidad']} "
            f"| Stock: {f['stock_actual']} | {f['disponibilidad']}\n"
            f"  Modelos: {f['modelos_compatibles']}\n"
        )
    return respuesta


@tool
def consultar_precio_repuesto(codigo: str) -> str:
    """
    Consulta el precio detallado y la disponibilidad de un repuesto por su código.
    Muestra precio de compra, precio de venta, margen y proveedor.

    Cuándo usar esta tool:
    - El cliente o técnico pregunta por el precio exacto de un repuesto
    - Se tiene el código del repuesto
    - Se necesita información completa de un ítem específico

    Parámetro:
      codigo: código exacto del repuesto. Ejemplo: 'MOT-001', 'FRE-003', 'ELE-001'.

    Ejemplos de preguntas:
    - "¿Cuánto vale el repuesto MOT-001?"
    - "Dame el precio del FRE-003"
    - "Información completa del ELE-002"
    """
    sql = f"""
        SELECT
            r.codigo,
            r.nombre,
            r.categoria,
            r.descripcion,
            r.precio_compra,
            r.precio_venta,
            ROUND(
                (r.precio_venta - r.precio_compra) * 100.0
                / NULLIF(r.precio_compra, 0), 1
            )                    AS margen_porcentaje,
            r.stock_actual,
            r.stock_minimo,
            r.unidad,
            p.nombre             AS proveedor,
            p.dias_entrega,
            CASE
                WHEN r.stock_actual = 0 THEN 'AGOTADO'
                WHEN r.stock_actual <= r.stock_minimo THEN 'STOCK BAJO'
                ELSE 'DISPONIBLE'
            END AS disponibilidad
        FROM repuestos r
        JOIN proveedores p ON p.id = r.id_proveedor
        WHERE r.codigo ILIKE '{codigo}'
    """
    filas = ejecutar_query(sql)

    if not filas:
        return f"No encontré ningún repuesto con el código '{codigo}'."

    f          = filas[0]
    p_compra   = f"${int(f['precio_compra']):,}".replace(",", ".")
    p_venta    = f"${int(f['precio_venta']):,}".replace(",", ".")

    respuesta  = f"DETALLE DEL REPUESTO {f['codigo']}\n"
    respuesta += "─" * 58 + "\n"
    respuesta += f"Nombre:          {f['nombre']}\n"
    respuesta += f"Categoría:       {f['categoria']}\n"
    respuesta += f"Descripción:     {f['descripcion']}\n"
    respuesta += f"Precio compra:   {p_compra} COP\n"
    respuesta += f"Precio venta:    {p_venta} COP / {f['unidad']}\n"
    respuesta += f"Margen:          {f['margen_porcentaje']}%\n"
    respuesta += f"Stock actual:    {f['stock_actual']} {f['unidad']}\n"
    respuesta += f"Stock mínimo:    {f['stock_minimo']} {f['unidad']}\n"
    respuesta += f"Disponibilidad:  {f['disponibilidad']}\n"
    respuesta += f"Proveedor:       {f['proveedor']}\n"
    respuesta += f"Tiempo entrega:  {f['dias_entrega']} días hábiles\n"
    return respuesta


@tool
def repuestos_agotados_o_bajos() -> str:
    """
    Lista todos los repuestos agotados o con stock por debajo del mínimo.
    Útil para planificar compras y evitar quedarse sin piezas clave.
    No requiere parámetros.

    Cuándo usar esta tool:
    - Preguntas sobre qué repuestos hay que pedir
    - Alertas de inventario
    - Planificación de compras
    - "¿Qué nos está faltando?"
    """
    sql = """
        SELECT
            r.codigo,
            r.nombre,
            r.categoria,
            r.stock_actual,
            r.stock_minimo,
            r.unidad,
            r.precio_compra,
            p.nombre   AS proveedor,
            p.dias_entrega,
            CASE
                WHEN r.stock_actual = 0 THEN 'AGOTADO'
                ELSE 'STOCK BAJO'
            END AS estado
        FROM repuestos r
        JOIN proveedores p ON p.id = r.id_proveedor
        WHERE r.stock_actual <= r.stock_minimo
          AND r.activo = 'SI'
        ORDER BY r.stock_actual ASC, r.categoria
    """
    filas = ejecutar_query(sql)

    if not filas:
        return "✅ Todos los repuestos tienen stock suficiente. No hay alertas."

    agotados = [f for f in filas if f["estado"] == "AGOTADO"]
    bajos    = [f for f in filas if f["estado"] == "STOCK BAJO"]

    respuesta  = f"⚠ ALERTA DE INVENTARIO — {len(filas)} repuesto(s) requieren atención\n"
    respuesta += "─" * 58 + "\n"

    if agotados:
        respuesta += f"\n❌ AGOTADOS ({len(agotados)}):\n"
        for f in agotados:
            p_compra = f"${int(f['precio_compra']):,}".replace(",", ".")
            respuesta += (
                f"  [{f['codigo']}] {f['nombre']}\n"
                f"  Stock: 0 {f['unidad']} | Proveedor: {f['proveedor']} "
                f"({f['dias_entrega']} días) | Costo aprox: {p_compra}\n"
            )

    if bajos:
        respuesta += f"\n⚠ STOCK BAJO ({len(bajos)}):\n"
        for f in bajos:
            p_compra = f"${int(f['precio_compra']):,}".replace(",", ".")
            respuesta += (
                f"  [{f['codigo']}] {f['nombre']}\n"
                f"  Stock: {f['stock_actual']}/{f['stock_minimo']} {f['unidad']} "
                f"| Proveedor: {f['proveedor']} | Costo: {p_compra}\n"
            )
    return respuesta


@tool
def consultar_proveedores() -> str:
    """
    Lista todos los proveedores activos con su calificación,
    tiempo de entrega y cuántos repuestos nos suministran.
    No requiere parámetros.

    Cuándo usar esta tool:
    - Preguntas sobre proveedores del taller
    - Ver quién nos vende los repuestos
    - Comparar tiempos de entrega entre proveedores
    """
    sql = """
        SELECT
            p.nombre,
            p.ciudad,
            p.contacto,
            p.telefono,
            p.dias_entrega,
            p.calificacion,
            COUNT(r.id) AS repuestos_suministrados
        FROM proveedores p
        LEFT JOIN repuestos r ON r.id_proveedor = p.id
        WHERE p.activo = 'SI'
        GROUP BY p.id, p.nombre, p.ciudad, p.contacto,
                 p.telefono, p.dias_entrega, p.calificacion
        ORDER BY p.calificacion DESC
    """
    filas = ejecutar_query(sql)

    respuesta  = f"PROVEEDORES ACTIVOS — {len(filas)}\n"
    respuesta += "─" * 58 + "\n"
    for f in filas:
        estrellas  = "★" * int(f["calificacion"]) + "☆" * (5 - int(f["calificacion"]))
        respuesta += (
            f"{f['nombre']} — {f['ciudad']}\n"
            f"  Calificación:  {estrellas} ({f['calificacion']})\n"
            f"  Entrega:       {f['dias_entrega']} días hábiles\n"
            f"  Contacto:      {f['contacto']} | {f['telefono']}\n"
            f"  Repuestos:     {f['repuestos_suministrados']} ítems\n"
        )
    return respuesta


# ──────────────────────────────────────────────────────────────────
# ENSAMBLAJE DEL AGENTE
# ──────────────────────────────────────────────────────────────────

tools = [
    consultar_repuestos,
    consultar_compatibilidad,
    consultar_precio_repuesto,
    repuestos_agotados_o_bajos,
    consultar_proveedores,
]

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

agente = create_react_agent(
    model=llm,
    tools=tools,
    prompt="""Eres el asistente de AutoTaller, un taller mecánico colombiano.
Tu trabajo es ayudar a técnicos y clientes a consultar la disponibilidad
y el precio de repuestos automotrices.

Puedes responder sobre:
- Disponibilidad y precios de repuestos
- Compatibilidad de piezas con marcas y modelos de vehículos
- Alertas de inventario (agotados o stock bajo)
- Información de proveedores

Responde siempre en español, de forma clara y amigable.
Cuando un repuesto esté agotado o con stock bajo, resáltalo claramente.
Si el cliente menciona una marca de vehículo, usa consultar_compatibilidad.
Si pregunta por un código específico, usa consultar_precio_repuesto."""
)


# ──────────────────────────────────────────────────────────────────
# LOOP CONVERSACIONAL
# ──────────────────────────────────────────────────────────────────

def iniciar_chat():
    print("\n" + "═" * 60)
    print("  🔧 AutoTaller — Consulta de Repuestos")
    print("  Escribe tu pregunta o 'salir' para terminar.")
    print("═" * 60)
    print("\n💡 Preguntas de ejemplo:")
    print("   → ¿Tienen pastillas de freno disponibles?")
    print("   → ¿Cuánto vale un filtro de aceite?")
    print("   → ¿Qué repuestos tienen para Toyota?")
    print("   → ¿Qué repuestos están agotados?")
    print("   → Dame el precio del repuesto MOT-004")
    print("   → ¿Tienen baterías en stock?\n")

    historial = []

    while True:
        pregunta = input("👤 Cliente/Técnico: ").strip()

        if pregunta.lower() in ("salir", "exit", "quit", "q"):
            print("\n👋 ¡Hasta luego!\n")
            break

        if not pregunta:
            continue

        historial.append({"role": "user", "content": pregunta})

        resultado  = agente.invoke({"messages": historial})
        respuesta  = resultado["messages"][-1].content

        print(f"\n🤖 AutoTaller:\n{respuesta}\n")
        print("─" * 60 + "\n")

        historial.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    iniciar_chat()