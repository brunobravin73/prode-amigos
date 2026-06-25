from fastapi import FastAPI
import os
from pydantic import BaseModel
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
        # Añadimos .order("fecha_partido", desc=False) para que queden en orden cronológico real
        respuesta_partidos = supabase.table("partidos")\
            .select("id, equipo_local, equipo_visitante, fecha_partido, estado, goles_local_real, goles_visitante_real")\
            .order("fecha_partido", desc=False)\
            .execute()
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
def guardar_o_actualizar_pronostico(datos: VotoPronostico): # <--- Usamos el modelo Pydantic para capturar el JSON
    try:
        # Extraemos los datos del modelo recibido
        usuario_id = datos.usuario_id
        partido_id = datos.partido_id
        goles_local_prediccion = datos.goles_local_prediccion
        goles_visitante_prediccion = datos.goles_visitante_prediccion

        # 1. Obtener la fecha del partido desde Supabase
        partido_res = supabase.table("partidos").select("fecha_partido").eq("id", partido_id).execute()
        if not partido_res.data:
            return {"status": "error", "message": "El partido no existe."}
        
        fecha_partido_str = partido_res.data[0]["fecha_partido"]
        
        # TRUCO: Cortamos el "+00" o "Z" del final
        if "+" in fecha_partido_str:
            fecha_partido_str = fecha_partido_str.split("+")[0]
        elif "Z" in fecha_partido_str:
            fecha_partido_str = fecha_partido_str.replace("Z", "")
            
        # Parseamos los números puros y asignamos huso horario de Argentina
        fecha_partido = datetime.fromisoformat(fecha_partido_str).replace(tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))

        # 2. Obtener la hora actual exacta de Argentina
        ahora_arg = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))

        # 3. La resta matemática de control (-20 minutos)
        tiempo_restante = fecha_partido - ahora_arg
        limite_tiempo = timedelta(minutes=20)

        if tiempo_restante < limite_tiempo:
            return {
                "status": "error", 
                "message": "Pronóstico bloqueado: El límite para registrar o modificar tu apuesta era hasta 20 minutos antes del inicio del partido."
            }

        # 4. Guardado o actualización normal...
        existente = supabase.table("pronosticos").select("id").eq("usuario_id", usuario_id).eq("partido_id", partido_id).execute()
        datos_pronostico = {
            "usuario_id": usuario_id,
            "partido_id": partido_id,
            "goles_local_prediccion": goles_local_prediccion,
            "goles_visitante_prediccion": goles_visitante_prediccion
        }

        if existente.data:
            id_prono = existente.data[0]["id"]
            supabase.table("pronosticos").update(datos_pronostico).eq("id", id_prono).execute()
            return {"status": "success", "message": "Pronóstico modificado correctamente"}
        else:
            supabase.table("pronosticos").insert(datos_pronostico).execute()
            return {"status": "success", "message": "Pronóstico creado correctamente"}

    except Exception as e:
        return {"status": "error", "message": repr(e)}

@app.post("/api/calcular-puntos/{partido_id}")
def calcular_puntos_partido(partido_id: int, goles_local_real: int, goles_visitante_real: int, clave_admin: str = None):
    try:
        # CONTROL DE SEGURIDAD: Definí acá tu contraseña secreta
        # Contraseña administrador:
        if clave_admin != os.environ.get("ADMIN_PASSWORD"):
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
        if clave_admin != os.environ.get("ADMIN_PASSWORD"):
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

@app.get("/api/partido/{partido_id}/pronosticos")
def ver_pronosticos_grupo(partido_id: int):
    try:
        # 1. Verificar si el partido ya está cerrado (finalizado o dentro de los 20 min previos)
        partido_res = supabase.table("partidos").select("fecha_partido, estado").eq("id", partido_id).execute()
        if not partido_res.data:
            return {"status": "error", "message": "El partido no existe."}
        
        partido = partido_res.data[0]
        fecha_partido_str = partido["fecha_partido"]
        estado = partido["estado"]
        
        if "+" in fecha_partido_str: fecha_partido_str = fecha_partido_str.split("+")[0]
        elif "Z" in fecha_partido_str: fecha_partido_str = fecha_partido_str.replace("Z", "")
        
        fecha_partido = datetime.fromisoformat(fecha_partido_str).replace(tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
        ahora_arg = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
        
        tiempo_restante = fecha_partido - ahora_arg
        es_cerrado = (estado == "finalizado") or (tiempo_restante < timedelta(minutes=20))
        
        # Candado de seguridad: Si no está cerrado, prohibido mirar
        if not es_cerrado:
            return {
                "status": "success", 
                "bloqueado": True, 
                "pronosticos": [], 
                "message": "🔒 Las apuestas del grupo se revelarán 20 minutos antes del inicio del partido."
            }
        
        # 2. Si pasó el candado, traemos las apuestas de este partido y los nombres de los usuarios
        pronos_res = supabase.table("pronosticos").select("usuario_id, goles_local_prediccion, goles_visitante_prediccion, puntos_ganados").eq("partido_id", partido_id).execute()
        usuarios_res = supabase.table("usuarios").select("id, nombre").execute()
        
        # Mapeamos los IDs de usuarios con sus nombres reales para cruzar la info rápido
        mapa_nombres = {u["id"]: u["nombre"] for u in usuarios_res.data}
        
        lista_revelada = []
        for p in pronos_res.data:
            lista_revelada.append({
                "nombre": mapa_nombres.get(p["usuario_id"], "Anónimo"),
                "voto": f"{p['goles_local_prediccion']} x {p['goles_visitante_prediccion']}",
                "puntos": p.get("puntos_ganados") if p.get("puntos_ganados") is not None else "-"
            })
            
        return {"status": "success", "bloqueado": False, "pronosticos": lista_revelada}
        
    except Exception as e:
        return {"status": "error", "message": repr(e)}
