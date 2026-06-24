from fastapi import FastAPI
import os
from pydantic import BaseModel
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone

# 1. Creamos la app principal de FastAPI
app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Modelos de Datos
class RegistroUsuario(BaseModel):
    nombre: str
    email: str
    password: str

class VotoPronostico(BaseModel):
    usuario_id: int
    partido_id: int
    goles_local_prediccion: int
    goles_visitante_prediccion: int

class LoginUsuario(BaseModel):
    email: str
    password: str

# --- RUTAS DE LA API (Todas van a responder con /api/...) ---

@app.get("/api")
def home():
    return {"status": "¡Prode Online!", "mensaje": "Bienvenido al prode con amigos"}

@app.get("/api/partidos")
def listar_partidos(usuario_id: int = None):
    try:
        # Añadimos goles_local_real y goles_visitante_real a la consulta
        respuesta_partidos = supabase.table("partidos").select("id, equipo_local, equipo_visitante, fecha_partido, estado, goles_local_real, goles_visitante_real").execute()
        partidos = respuesta_partidos.data
        
        pronosticos_dic = {}
        if usuario_id:
            respuesta_pronos = supabase.table("pronosticos").select("partido_id, goles_local_prediccion, goles_visitante_prediccion").eq("usuario_id", usuario_id).execute()
            for p in respuesta_pronos.data:
                pronosticos_dic[p["partido_id"]] = p

        for partido in partidos:
            id_p = partido["id"]
            if id_p in pronosticos_dic:
                partio_prono = pronosticos_dic[id_p]
                partido["voto_local"] = partio_prono["goles_local_prediccion"]
                partido["voto_visitante"] = partio_prono["goles_visitante_prediccion"]
            else:
                partido["voto_local"] = ""
                partido["voto_visitante"] = ""

        return {"status": "success", "partidos": partidos}
    except Exception as e:
        return {"status": "error", "message": repr(e)}

@app.post("/api/registro")
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

@app.post("/api/login")
def login_usuario(datos: LoginUsuario):
    try:
        # 1. Buscamos el usuario por email
        respuesta = supabase.table("usuarios").select("*").eq("email", datos.email).execute()
        
        # Si no encuentra ninguna fila, el mail no existe
        if not respuesta.data:
            return {"status": "error", "message": "El correo electrónico no está registrado."}
            
        usuario = respuesta.data[0]
        
        # 2. Comparamos la contraseña (por ahora en texto plano, directo)
        if usuario["password_hash"] != datos.password:
            return {"status": "error", "message": "Contraseña incorrecta."}
            
        # 3. Si coincide, logueado con éxito
        return {
            "status": "success", 
            "mensaje": "Ingreso exitoso", 
            "usuario": {
                "id": usuario["id"],
                "nombre": usuario["nombre"],
                "puntos_totales": usuario["puntos_totales"]
            }
        }
    except Exception as e:
        return {"status": "error", "message": repr(e)}

@app.post("/api/pronostico")
def guardar_o_actualizar_pronostico(usuario_id: int, partido_id: int, goles_local_prediccion: int, goles_visitante_prediccion: int):
    try:
        # 1. Verificar si el usuario ya hizo un pronóstico previo para este partido
        existente = supabase.table("pronosticos").select("id").eq("usuario_id", usuario_id).eq("partido_id", partido_id).execute()
        
        datos_pronostico = {
            "usuario_id": usuario_id,
            "partido_id": partido_id,
            "goles_local_prediccion": goles_local_prediccion,
            "goles_visitante_prediccion": goles_visitante_prediccion
        }

        if existente.data:
            # Si ya existía, lo actualizamos (Modificación)
            id_prono = existente.data[0]["id"]
            supabase.table("pronosticos").update(datos_pronostico).eq("id", id_prono).execute()
            return {"status": "success", "message": "Pronóstico modificado correctamente"}
        else:
            # Si es nuevo, lo insertamos (Guardado inicial)
            supabase.table("pronosticos").insert(datos_pronostico).execute()
            return {"status": "success", "message": "Pronóstico creado correctamente"}

    except Exception as e:
        return {"status": "error", "message": repr(e)}

@app.post("/api/calcular-puntos/{partido_id}")
def calcular_puntos_partido(partido_id: int, goles_local_real: int, goles_visitante_real: int, clave_admin: str = None):
    try:
        # CONTROL DE SEGURIDAD: Definí acá tu contraseña secreta
        # Contraseña administrador:
        if clave_admin != "ladorni737$ñ":
            return {"status": "error", "message": "Clave de administrador incorrecta o ausente."}

        # 1. Actualizar el partido con el resultado real y pasarlo a 'finalizado'
        supabase.table("partidos").update({
            "goles_local_real": goles_local_real,
            "goles_visitante_real": goles_visitante_real,
            "estado": "finalizado"
        }).eq("id", partido_id).execute()

        # 2. Traer todos los pronósticos que hicieron tus amigos para este partido
        pronosticos = supabase.table("pronosticos").select("*").eq("partido_id", partido_id).execute()

        puntos_repartidos = []

        # 3. Analizar voto por voto aplicando las reglas
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
                # Determinar tendencia real
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
            user_data = supabase.table("usuarios").select("puntos_totales").eq("id", user_id).execute()
            puntos_actuales = user_data.data[0]["puntos_totales"] or 0
            
            supabase.table("usuarios").update({"puntos_totales": puntos_actuales + puntos}).eq("id", user_id).execute()

            puntos_repartidos.append({"usuario_id": user_id, "puntos_asignados": puntos})

        return {"status": "success", "mensaje": "Puntos calculados con éxito", "detalle": puntos_repartidos}

    except Exception as e:
        return {"status": "error", "message": repr(e)}

@app.get("/api/posiciones")
def obtener_tabla_posiciones():
    try:
        respuesta = supabase.table("usuarios").select("id, nombre, puntos_totales").order("puntos_totales", desc=True).execute()
        return {"status": "success", "tabla": respuesta.data}
    except Exception as e:
        return {"status": "error", "message": repr(e)}

@app.post("/api/crear-partido")
def crear_nuevo_partido(equipo_local: str, equipo_visitante: str, fecha_partido: str, clave_admin: str = None):
    try:
        if clave_admin != "ladorni737$ñ":
            return {"status": "error", "message": "Clave de administrador incorrecta."}

        # Insertamos el partido nuevo directo en Supabase
        respuesta = supabase.table("partidos").insert({
            "equipo_local": equipo_local,
            "equipo_visitante": equipo_visitante,
            "fecha_partido": fecha_partido,
            "estado": "pendiente"
        }).execute()

        return {"status": "success", "partido": respuesta.data[0]}
    except Exception as e:
        return {"status": "error", "message": repr(e)}
