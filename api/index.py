from fastapi import FastAPI
import os
from supabase import create_client, Client

app = FastAPI()

# Conseguí estos datos en el panel de Supabase: Settings -> API
SUPABASE_URL = os.environ.get("SUPABASE_URL", "TU_SUPABASE_URL_AQUÍ")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "TU_SUPABASE_ANON_KEY_AQUÍ")

# Creamos el cliente oficial
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.get("/")
def home():
    return {"status": "¡Prode Online!", "mensaje": "Bienvenido al prode con amigos"}

@app.get("/partidos")
def listar_partidos():
    try:
        # Traemos los datos de la tabla 'partidos' usando la librería oficial
        respuesta = supabase.table("partidos").select("id, equipo_local, equipo_visitante, fecha_partido, estado").execute()
        return {"status": "success", "partidos": respuesta.data}
    except Exception as e:
        return {"status": "error", "message": repr(e)}
