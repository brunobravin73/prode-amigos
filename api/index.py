from fastapi import FastAPI, HTTPException
import os
from pydantic import BaseModel
from supabase import create_client, Client

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

# NUEVA RUTA: Guardar el pronóstico de un amigo
@app.post("/pronostico")
def guardar_pronostico(datos: VotoPronostico):
    try:
        nuevo_voto = {
            "usuario_id": datos.usuario_id,
            "partido_id": datos.partido_id,
            "goles_local_prediccion": datos.goles_local_prediccion,
            "goles_visitante_prediccion": datos.goles_visitante_prediccion
        }
        # Gracias al UNIQUE que pusimos en SQL, si intenta votar dos veces el mismo partido, fallará
        respuesta = supabase.table("pronosticos").insert(nuevo_voto).execute()
        return {"status": "success", "mensaje": "Pronóstico guardado", "datos": respuesta.data}
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
