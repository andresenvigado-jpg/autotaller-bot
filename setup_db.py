"""
╔══════════════════════════════════════════════════════════════╗
║  MÓDULO 1 — setup_db.py (Taller Automotriz)                 ║
║  Qué hace: Destruye las tablas anteriores y crea el         ║
║            esquema nuevo para un taller mecánico con        ║
║            catálogo de repuestos, proveedores y stock.      ║
║  Ejecutar: python setup_db.py                               ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String,
    Date, DateTime, ForeignKey, Text, Numeric, text
)
from sqlalchemy.orm import declarative_base, Session
from faker import Faker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine       = create_engine(DATABASE_URL, echo=False)
Base         = declarative_base()
fake         = Faker("es_CO")
random.seed(42)


# ──────────────────────────────────────────────────────────────────
# TABLAS
# ──────────────────────────────────────────────────────────────────

class Proveedor(Base):
    """Empresas que nos venden los repuestos."""
    __tablename__ = "proveedores"

    id           = Column(Integer, primary_key=True)
    nombre       = Column(String(120), nullable=False)
    ciudad       = Column(String(80))
    contacto     = Column(String(100))
    telefono     = Column(String(20))
    email        = Column(String(100))
    dias_entrega = Column(Integer)       # Días promedio de entrega
    calificacion = Column(Numeric(3, 1)) # 1.0 – 5.0
    activo       = Column(String(2), default="SI")


class Marca(Base):
    """Marcas de vehículos compatibles con los repuestos."""
    __tablename__ = "marcas"

    id     = Column(Integer, primary_key=True)
    nombre = Column(String(60), nullable=False)  # Toyota, Chevrolet, Renault...


class Repuesto(Base):
    """
    Catálogo de repuestos disponibles en el taller.
    Cada repuesto tiene precio, stock y compatibilidad con marcas.
    """
    __tablename__ = "repuestos"

    id              = Column(Integer, primary_key=True)
    codigo          = Column(String(30), unique=True, nullable=False)
    nombre          = Column(String(150), nullable=False)
    categoria       = Column(String(60))   # Motor, Frenos, Suspensión, Eléctrico...
    descripcion     = Column(Text)
    precio_compra   = Column(Numeric(12, 2))  # Precio al que lo compramos
    precio_venta    = Column(Numeric(12, 2))  # Precio al que lo vendemos
    stock_actual    = Column(Integer)
    stock_minimo    = Column(Integer)         # Alerta si bajamos de aquí
    unidad          = Column(String(20))      # Unidad, Par, Kit, Litro...
    id_proveedor    = Column(Integer, ForeignKey("proveedores.id"))
    activo          = Column(String(2), default="SI")


class RepuestoMarca(Base):
    """
    Tabla de compatibilidad: qué repuesto es compatible con qué marca.
    Un repuesto puede ser compatible con varias marcas y modelos.
    """
    __tablename__ = "repuesto_marca"

    id          = Column(Integer, primary_key=True)
    id_repuesto = Column(Integer, ForeignKey("repuestos.id"))
    id_marca    = Column(Integer, ForeignKey("marcas.id"))
    modelos     = Column(String(200))  # "Corolla 2015-2023, Yaris 2018-2023"


class MovimientoStock(Base):
    """
    Historial de entradas y salidas de repuestos.
    Entrada: compramos repuestos al proveedor.
    Salida:  vendemos/usamos un repuesto en un servicio.
    """
    __tablename__ = "movimientos_stock"

    id          = Column(Integer, primary_key=True)
    id_repuesto = Column(Integer, ForeignKey("repuestos.id"))
    tipo        = Column(String(10))      # Entrada o Salida
    cantidad    = Column(Integer)
    fecha       = Column(DateTime, nullable=False)
    motivo      = Column(String(150))     # "Compra OC-001", "Servicio vehículo ABC123"
    responsable = Column(String(100))


# ──────────────────────────────────────────────────────────────────
# DATOS SINTÉTICOS
# ──────────────────────────────────────────────────────────────────

NOMBRES_PROVEEDORES = [
    "Autopartes del Norte S.A.S",
    "Distribuidora Repuestos Medellín",
    "Importadora AutoTech Ltda",
    "Repuestos Originales Colombia",
    "Multirepuestos del Eje Cafetero",
    "Proveedora Nacional de Autopartes",
]

MARCAS_VEHICULOS = [
    "Toyota", "Chevrolet", "Renault", "Mazda",
    "Hyundai", "Kia", "Nissan", "Ford"
]

# (código, nombre, categoría, descripción, precio_compra, precio_venta, stock, mínimo, unidad)
CATALOGO_REPUESTOS = [
    # MOTOR
    ("MOT-001", "Filtro de aceite",               "Motor",      "Filtro para aceite de motor, uso general",                  18000,  35000, 45, 10, "Unidad"),
    ("MOT-002", "Filtro de aire",                  "Motor",      "Filtro de aire para motor de combustión interna",           22000,  42000, 30,  8, "Unidad"),
    ("MOT-003", "Bujía de encendido",              "Motor",      "Bujía estándar de cobre para motor a gasolina",             12000,  25000, 80, 20, "Unidad"),
    ("MOT-004", "Correa de distribución",          "Motor",      "Correa dentada para sincronización del motor",              85000, 160000, 15,  5, "Unidad"),
    ("MOT-005", "Empaque de culata",               "Motor",      "Empaque de sellado entre bloque y culata",                 120000, 220000,  8,  3, "Unidad"),
    ("MOT-006", "Aceite de motor 20W-50 1L",       "Motor",      "Aceite mineral multigrado para motor a gasolina",           18000,  32000, 60, 15, "Litro"),
    ("MOT-007", "Kit de distribución completo",    "Motor",      "Incluye correa, tensor y bomba de agua",                  280000, 480000,  6,  2, "Kit"),
    ("MOT-008", "Tapa de válvulas",                "Motor",      "Cubierta superior del motor, incluye empaque",              95000, 170000,  5,  2, "Unidad"),

    # FRENOS
    ("FRE-001", "Pastillas de freno delanteras",   "Frenos",     "Pastillas semimetálicas para freno de disco delantero",     65000, 120000, 25,  6, "Par"),
    ("FRE-002", "Pastillas de freno traseras",     "Frenos",     "Pastillas semimetálicas para freno de disco trasero",       55000, 100000, 20,  5, "Par"),
    ("FRE-003", "Disco de freno delantero",        "Frenos",     "Disco ventilado para eje delantero",                       110000, 195000, 12,  4, "Unidad"),
    ("FRE-004", "Disco de freno trasero",          "Frenos",     "Disco sólido para eje trasero",                             90000, 165000, 10,  3, "Unidad"),
    ("FRE-005", "Líquido de frenos DOT4 500ml",    "Frenos",     "Líquido hidráulico para sistema de frenos",                 15000,  28000, 35,  8, "Unidad"),
    ("FRE-006", "Tambor de freno trasero",         "Frenos",     "Tambor de freno para vehículos con freno de tambor",        98000, 175000,  8,  3, "Unidad"),
    ("FRE-007", "Zapatas de freno",                "Frenos",     "Zapatas con material de fricción para freno de tambor",     48000,  88000, 15,  4, "Par"),

    # SUSPENSIÓN
    ("SUS-001", "Amortiguador delantero",          "Suspensión", "Amortiguador hidráulico para eje delantero",               185000, 320000,  8,  2, "Unidad"),
    ("SUS-002", "Amortiguador trasero",            "Suspensión", "Amortiguador hidráulico para eje trasero",                 165000, 290000,  8,  2, "Unidad"),
    ("SUS-003", "Resorte helicoidal delantero",    "Suspensión", "Resorte de suspensión delantera",                          120000, 210000,  6,  2, "Unidad"),
    ("SUS-004", "Barra estabilizadora delantera",  "Suspensión", "Barra anti-balanceo para eje delantero",                    95000, 170000,  5,  2, "Unidad"),
    ("SUS-005", "Rotula de suspensión",            "Suspensión", "Rótula inferior de suspensión delantera",                   75000, 135000, 10,  3, "Unidad"),
    ("SUS-006", "Buje de suspensión",              "Suspensión", "Buje de caucho para brazos de suspensión",                  28000,  52000, 20,  5, "Unidad"),
    ("SUS-007", "Terminal de dirección",           "Suspensión", "Terminal de barra de dirección lado derecho/izquierdo",     68000, 122000, 12,  3, "Unidad"),

    # ELÉCTRICO
    ("ELE-001", "Batería 45Ah",                    "Eléctrico",  "Batería de plomo-ácido 12V 45Ah para vehículos pequeños",  280000, 420000,  8,  2, "Unidad"),
    ("ELE-002", "Batería 60Ah",                    "Eléctrico",  "Batería de plomo-ácido 12V 60Ah para vehículos medianos",  340000, 510000,  6,  2, "Unidad"),
    ("ELE-003", "Alternador remanufacturado",       "Eléctrico",  "Alternador revisado y garantizado 12V 90A",               320000, 550000,  4,  1, "Unidad"),
    ("ELE-004", "Motor de arranque",               "Eléctrico",  "Motor de arranque remanufacturado 12V",                   290000, 490000,  4,  1, "Unidad"),
    ("ELE-005", "Bobina de encendido",             "Eléctrico",  "Bobina de alta tensión para sistema de encendido",         95000, 165000,  8,  2, "Unidad"),
    ("ELE-006", "Sensor de oxígeno",               "Eléctrico",  "Sensor lambda para control de mezcla aire-combustible",   145000, 250000,  6,  2, "Unidad"),
    ("ELE-007", "Sensor de temperatura del motor", "Eléctrico",  "Sensor ECT para control de temperatura",                   55000,  98000, 10,  3, "Unidad"),

    # TRANSMISIÓN
    ("TRA-001", "Kit de embrague completo",        "Transmisión","Disco, plato y rodamiento de embrague",                   380000, 620000,  4,  1, "Kit"),
    ("TRA-002", "Aceite de caja manual 80W-90",    "Transmisión","Aceite para caja de velocidades manual",                   22000,  40000, 25,  6, "Litro"),
    ("TRA-003", "Aceite ATF para caja automática", "Transmisión","Aceite para transmisión automática",                       28000,  50000, 20,  5, "Litro"),
    ("TRA-004", "Cruceta de cardán",               "Transmisión","Cruceta universal para árbol de transmisión",              85000, 148000,  6,  2, "Unidad"),
    ("TRA-005", "Bota de homocinética",            "Transmisión","Bota de caucho para junta homocinética",                   45000,  82000, 15,  4, "Unidad"),

    # REFRIGERACIÓN
    ("REF-001", "Termostato de motor",             "Refrigeración","Termostato 82°C para control de temperatura",            38000,  68000, 12,  3, "Unidad"),
    ("REF-002", "Anticongelante 1L",               "Refrigeración","Refrigerante concentrado para sistema de enfriamiento",  18000,  32000, 40, 10, "Litro"),
    ("REF-003", "Bomba de agua",                   "Refrigeración","Bomba centrífuga para circulación del refrigerante",    145000, 248000,  6,  2, "Unidad"),
    ("REF-004", "Manguera superior de radiador",   "Refrigeración","Manguera de caucho para salida del radiador",            35000,  62000, 10,  3, "Unidad"),
    ("REF-005", "Tapa de radiador",                "Refrigeración","Tapa con válvula de presión para radiador",               22000,  40000, 15,  4, "Unidad"),

    # DIRECCIÓN
    ("DIR-001", "Líquido de dirección hidráulica", "Dirección",  "Fluido para caja de dirección asistida",                   18000,  32000, 20,  5, "Litro"),
    ("DIR-002", "Bomba de dirección hidráulica",   "Dirección",  "Bomba de paletas para dirección asistida",                295000, 490000,  3,  1, "Unidad"),
    ("DIR-003", "Cremallera de dirección",         "Dirección",  "Rack de dirección remanufacturado",                       480000, 780000,  2,  1, "Unidad"),
]

# Modelos de vehículos por marca para la compatibilidad
MODELOS_POR_MARCA = {
    "Toyota":    "Corolla 2010-2023, Yaris 2015-2023, Hilux 2010-2023, RAV4 2012-2023",
    "Chevrolet": "Spark 2010-2023, Sail 2012-2022, Captiva 2010-2020, Tracker 2015-2023",
    "Renault":   "Logan 2010-2023, Sandero 2010-2023, Duster 2012-2023, Kwid 2017-2023",
    "Mazda":     "Mazda 3 2010-2023, Mazda 6 2010-2020, CX-5 2013-2023, BT-50 2012-2022",
    "Hyundai":   "i10 2012-2023, Accent 2010-2023, Tucson 2010-2023, Santa Fe 2010-2022",
    "Kia":       "Picanto 2012-2023, Rio 2012-2023, Sportage 2010-2023, Sorento 2010-2022",
    "Nissan":    "March 2012-2023, Sentra 2013-2023, X-Trail 2010-2023, Frontier 2010-2023",
    "Ford":      "Fiesta 2010-2019, Focus 2010-2020, Explorer 2010-2023, Ranger 2010-2023",
}

CIUDADES_CO = ["Medellín", "Bogotá", "Cali", "Bucaramanga",
               "Pereira", "Manizales", "Itagüí", "Bello"]


# ──────────────────────────────────────────────────────────────────
# FUNCIONES DE INSERCIÓN
# ──────────────────────────────────────────────────────────────────

def insertar_proveedores(session: Session) -> list:
    ids = []
    for nombre in NOMBRES_PROVEEDORES:
        p = Proveedor(
            nombre       = nombre,
            ciudad       = random.choice(CIUDADES_CO),
            contacto     = fake.name(),
            telefono     = fake.phone_number(),
            email        = fake.email(),
            dias_entrega = random.randint(1, 7),
            calificacion = round(random.uniform(3.5, 5.0), 1),
            activo       = "SI",
        )
        session.add(p)
        session.flush()
        ids.append(p.id)
    return ids


def insertar_marcas(session: Session) -> dict:
    """Retorna diccionario {nombre_marca: id}"""
    ids = {}
    for nombre in MARCAS_VEHICULOS:
        m = Marca(nombre=nombre)
        session.add(m)
        session.flush()
        ids[nombre] = m.id
    return ids


def insertar_repuestos(session: Session, ids_proveedores: list) -> list:
    ids = []
    for datos in CATALOGO_REPUESTOS:
        codigo, nombre, cat, desc, p_compra, p_venta, stock, minimo, unidad = datos

        # Variamos stock ±30% para simular fluctuación real
        stock_real = max(0, int(stock * random.uniform(0.7, 1.3)))

        r = Repuesto(
            codigo        = codigo,
            nombre        = nombre,
            categoria     = cat,
            descripcion   = desc,
            precio_compra = p_compra,
            precio_venta  = p_venta,
            stock_actual  = stock_real,
            stock_minimo  = minimo,
            unidad        = unidad,
            id_proveedor  = random.choice(ids_proveedores),
            activo        = "SI",
        )
        session.add(r)
        session.flush()
        ids.append(r.id)
    return ids


def insertar_compatibilidades(session: Session, ids_repuestos: list, ids_marcas: dict):
    """Asigna compatibilidad aleatoria: cada repuesto es compatible con 2-5 marcas."""
    marcas_lista = list(ids_marcas.keys())
    for id_rep in ids_repuestos:
        num_marcas = random.randint(2, 5)
        marcas_compatibles = random.sample(marcas_lista, k=num_marcas)
        for marca in marcas_compatibles:
            rm = RepuestoMarca(
                id_repuesto = id_rep,
                id_marca    = ids_marcas[marca],
                modelos     = MODELOS_POR_MARCA[marca],
            )
            session.add(rm)


def insertar_movimientos(session: Session, ids_repuestos: list):
    """Crea historial de entradas y salidas de stock de los últimos 90 días."""
    hoy = datetime.today()
    motivos_salida = [
        "Servicio vehículo {placa}",
        "Venta mostrador",
        "Garantía reposición",
    ]
    for id_rep in ids_repuestos:
        # Entre 3 y 8 movimientos por repuesto
        for _ in range(random.randint(3, 8)):
            tipo = random.choices(["Entrada", "Salida"], weights=[40, 60])[0]
            cantidad = random.randint(1, 10) if tipo == "Entrada" else random.randint(1, 3)
            placa = f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(100,999)}"
            motivo = (
                f"Compra OC-{random.randint(1,30):04d}"
                if tipo == "Entrada"
                else random.choice(motivos_salida).format(placa=placa)
            )
            mov = MovimientoStock(
                id_repuesto = id_rep,
                tipo        = tipo,
                cantidad    = cantidad,
                fecha       = hoy - timedelta(days=random.randint(1, 90)),
                motivo      = motivo,
                responsable = fake.name(),
            )
            session.add(mov)


# ──────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 55)
    print("  AutoTaller — Configuración de base de datos")
    print("═" * 55)

    print("\n🔧 Paso 1: Eliminando tablas anteriores y creando nuevas...")
    
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    
    
    Base.metadata.create_all(engine)  # Crea las nuevas
    print("   ✅ 5 tablas creadas: proveedores, marcas, repuestos,")
    print("                        repuesto_marca, movimientos_stock")

    print("\n📦 Paso 2: Insertando datos sintéticos...")
    with Session(engine) as session:

        ids_prov   = insertar_proveedores(session)
        print(f"   ✔  Proveedores:       {len(ids_prov)}")

        ids_marcas = insertar_marcas(session)
        print(f"   ✔  Marcas:            {len(ids_marcas)}")

        ids_rep    = insertar_repuestos(session, ids_prov)
        print(f"   ✔  Repuestos:         {len(ids_rep)}")

        insertar_compatibilidades(session, ids_rep, ids_marcas)
        print(f"   ✔  Compatibilidades:  asignadas")

        insertar_movimientos(session, ids_rep)
        print(f"   ✔  Movimientos stock: generados")

        session.commit()
        print("\n   💾 Datos guardados en PostgreSQL.")

    print("\n🔍 Paso 3: Verificando registros...")
    tablas = ["proveedores", "marcas", "repuestos", "repuesto_marca", "movimientos_stock"]
    with engine.connect() as conn:
        for tabla in tablas:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            print(f"   📋 {tabla:<25} → {n} filas")

    print("\n🎉 ¡Base de datos lista! Ahora ejecuta: python agente_repuestos.py")
    print("═" * 55 + "\n")


if __name__ == "__main__":
    main()