from fastapi import FastAPI
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    # Añadimos sslmode para asegurar que conecte de forma encriptada a Supabase
    if DATABASE_URL and "sslmode" not in DATABASE_URL:
        # Si la URL no tiene el parámetro de SSL, se lo agregamos
        connect_url = f"{DATABASE_URL}?sslmode=require"
    else:
        connect_url = DATABASE_URL
        
    return psycopg2.connect(connect_url)

@app.get("/")
def home():
    return {"status": "¡Prode Online!", "mensaje": "Bienvenido al prode con amigos"}

@app.get("/partidos")
def listar_partidos():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, equipo_local, equipo_visitante, fecha_partido, estado FROM partidos;")
        partidos = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "success", "partidos": partidos}
    except Exception as e:
        # Usamos repr(e) para que nos traiga el nombre real del error técnico
        return {"status": "error", "message": repr(e)}
