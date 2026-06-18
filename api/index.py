from fastapi import FastAPI
import os
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Creamos un "Modelo" para definir qué datos necesitamos recibir al registrar un usuario
class RegistroUsuario(BaseModel):
    nombre: str
    email: str
    password: str

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

# NUEVA RUTA: Registrar un usuario nuevo
@app.post("/registro")
def registrar_usuario(datos: RegistroUsuario):
    try:
        # Insertamos el nuevo usuario en la base de datos
        nuevo_usuario = {
            "nombre": datos.nombre,
            "email": datos.email,
            "password_hash": datos.password # Temporalmente directo para probar
        }
        
        respuesta = supabase.table("usuarios").insert(nuevo_usuario).execute()
        
        return {"status": "success", "mensaje": "Usuario registrado con éxito", "usuario": respuesta.data}
    except Exception as e:
        return {"status": "error", "message": repr(e)}
