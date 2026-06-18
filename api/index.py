from fastapi import FastAPI
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()

# Vercel va a tomar la variable de entorno que configuraste en su panel
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

@app.get("/")
def home():
    return {"status": "¡Prode Online!", "mensaje": "Bienvenido al prode con amigos"}

@app.get("/partidos")
def listar_partidos():
    try:
        conn = get_db_connection()
        # Usamos RealDictCursor para que nos devuelva los datos en formato JSON (clave: valor)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, equipo_local, equipo_visitante, fecha_partido, estado FROM partidos;")
        partidos = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "success", "partidos": partidos}
    except Exception as e:
        return {"status": "error", "message": str(e)}
