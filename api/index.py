from fastapi import FastAPI, HTTPException
import os
from pydantic import BaseModel
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Modelo para recibir un usuario nuevo
class RegistroUsuario(BaseModel):
    nombre: str
    email: str
    password: str

# NUEVO MODELO: Para recibir la votación de un partido
class VotoPronostico(BaseModel):
    usuario_id: int
    partido_id: int
    goles_local_prediccion: int
    goles_visitante_prediccion: int

@app.get("/")
def home():
    return {"status": "¡Prode Online!", "mensaje": "Bienvenido al prode con amigos"}

@app.get("/partidos")
def listar_partidos():
    try:
        respuesta = supabase.table("partidos").select("id, equipo_local, equipo_visitante, fecha_partido, estado").execute()
        return {"status": "success", "partidos": respuesta.data}
    except Exception as e:
        return {"status": "error", "message": repr(e)}

@app.post("/registro")
def registrar_usuario(datos: RegistroUsuario):
    try:
        nuevo_usuario = {
            "nombre": datos.nombre,
            "email": datos.email,
            "password_hash": datos.password
        }
        respuesta = supabase.table("usuarios").insert(nuevo_usuario).execute()
        return {"status": "success", "mensaje": "Usuario registrado con éxito", "usuario": respuesta.data}
    except Exception as e:
        return {"status": "error", "message": repr(e)}

# Guardar el pronóstico
@app.post("/pronostico")
def guardar_pronostico(datos: VotoPronostico):
    try:
        # 1. Buscar a qué hora se juega el partido en la base de datos
        partido_data = supabase.table("partidos").select("fecha_partido, equipo_local, equipo_visitante").eq("id", datos.partido_id).execute()
        
        if not partido_data.data:
            return {"status": "error", "message": "El partido especificado no existe."}
            
        # Tomamos la fecha del partido (viene como texto de la base de datos)
        # PostgreSQL la devuelve en formato ISO (ej: '2026-06-25T21:00:00+00:00')
        fecha_partido_str = partido_data.data[0]["fecha_partido"]
        
        # Convertimos ese texto en un objeto de fecha de Python con Zona Horaria
        fecha_partido = datetime.fromisoformat(fecha_partido_str)
        
        # 2. Obtener la hora actual exacta (en UTC, que es el estándar de internet)
        ahora = datetime.now(timezone.utc)
        
        # 3. Definir el límite (ejemplo: 2 horas antes del partido)
        # Podés cambiar el 'hours=2' por el tiempo que vos quieras (ej: hours=1, o minutes=30)
        limite_votacion = fecha_partido - timedelta(hours=2)
        
        # 4. Controlar el reloj
        if ahora > limite_votacion:
            # Si ya pasamos el límite de tiempo
            return {
                "status": "bloqueado", 
                "message": f"Ya no podés modificar este partido. El límite era 2 horas antes del comienzo."
            }
            
        # 5. Si pasó el control de hora, procedemos a guardar/actualizar como antes
        nuevo_voto = {
            "usuario_id": datos.usuario_id,
            "partido_id": datos.partido_id,
            "goles_local_prediccion": datos.goles_local_prediccion,
            "goles_visitante_prediccion": datos.goles_visitante_prediccion,
            "puntos_ganados": 0
        }
        
        respuesta = supabase.table("pronosticos").upsert(
            nuevo_voto, 
            on_conflict="usuario_id,partido_id"
        ).execute()
        
        return {"status": "success", "mensaje": "Pronóstico guardado/actualizado con éxito", "datos": respuesta.data}
        
    except Exception as e:
        return {"status": "error", "message": repr(e)}

# NUEVA RUTA: El cerebro que calcula los puntos según tus reglas
@app.post("/calcular-puntos/{partido_id}")
def calcular_puntos_partido(partido_id: int, goles_local_real: int, goles_visitante_real: int):
    try:
        # 1. Actualizar el partido con el resultado real y pasarlo a 'finalizado'
        supabase.table("partidos").update({
            "goles_local_real": goles_local_real,
            "goles_visitante_real": goles_visitante_real,
            "estado": "finalizado"
        }).eq("id", partido_id).execute()

        # 2. Traer todos los pronósticos que hicieron tus amigos para este partido
        pronosticos = supabase.table("pronosticos").select("*").eq("partido_id", partido_id).execute()

        puntos_repartidos = []

        # 3. Analizar voto por voto aplicando las reglas de Bruno
        for p in pronosticos.data:
            id_voto = p["id"]
            user_id = p["usuario_id"]
            gl_pred = p["goles_local_prediccion"]
            gv_pred = p["goles_visitante_prediccion"]

            puntos = 0

            # REGLA 1: Resultado Perfecto (3 puntos)
            if gl_pred == goles_local_real and gv_pred == goles_visitante_real:
                puntos = 3
            else:
                # Determinar tendencia real (1 = Gana Local, 2 = Gana Visitante, 0 = Empate)
                if goles_local_real > goles_visitante_real: tendencia_real = 1
                elif goles_local_real < goles_visitante_real: tendencia_real = 2
                else: tendencia_real = 0

                # Determinar tendencia de la predicción
                if gl_pred > gv_pred: tendencia_pred = 1
                elif gl_pred < gv_pred: tendencia_pred = 2
                else: tendencia_pred = 0

                # REGLA 2: Acertó ganador o empate (1 punto)
                if tendencia_real == tendencia_pred:
                    puntos = 1

            # 4. Guardar los puntos ganados en ese pronóstico específico
            supabase.table("pronosticos").update({"puntos_ganados": puntos}).eq("id", id_voto).execute()

            # 5. Sumar esos puntos al total acumulado del usuario en la tabla 'usuarios'
            # Primero buscamos cuántos puntos tenía
            user_data = supabase.table("usuarios").select("puntos_totales").eq("id", user_id).execute()
            puntos_actuales = user_data.data[0]["puntos_totales"] or 0
            
            # Actualizamos sumando lo nuevo
            supabase.table("usuarios").update({"puntos_totales": puntos_actuales + puntos}).eq("id", user_id).execute()

            puntos_repartidos.append({"usuario_id": user_id, "puntos_asignados": puntos})

        return {"status": "success", "mensaje": "Puntos calculados y posiciones actualizadas", "detalle": puntos_repartidos}

    except Exception as e:
        return {"status": "error", "message": repr(e)}


# Tabla de posiciones en tiempo real
@app.get("/posiciones")
def obtener_tabla_posiciones():
    try:
        # Traemos el nombre, email y puntos de los usuarios, ordenados por puntos de forma descendente (desc=True)
        respuesta = supabase.table("usuarios")\
            .select("id, nombre, puntos_totales")\
            .order("puntos_totales", desc=True)\
            .execute()
            
        return {"status": "success", "tabla": respuesta.data}
    except Exception as e:
        return {"status": "error", "message": repr(e)}
