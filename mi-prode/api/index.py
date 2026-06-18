from fastapi import FastAPI
import os
import psycopg2
from pydantic import BaseModel

app = FastAPI()

# Esta URL la vas a sacar de tu panel de Supabase (Paso 3)
# Por seguridad, en producción se usa una variable de entorno
DATABASE_URL = os.environ.get("postgresql://postgres:kbHOAhjlfBYTg00T@db.ypedflapmsozywmfbjut.supabase.co:5432/postgres")

def get_db_connection():
    # Función auxiliar para conectarse a PostgreSQL
    conn = psycopg2.connect(DATABASE_URL)
    return conn

@app.get("/")
def home():
    return {"status": "¡Prode Online!", "mensaje": "Bienvenido al prode con amigos"}

@app.get("/test-db")
def test_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()
        cur.close()
        conn.close()
        return {"status": "Conexión exitosa a Supabase", "version": db_version[0]}
    except Exception as e:
        return {"status": "Error de conexión", "error": str(e)}
