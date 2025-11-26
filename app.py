# hash_passwords_once.py

import os
import bcrypt
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en el .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def hash_password(plain: str) -> str:
    # bcrypt genera un hash con salt interno
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def main():
    # Aquí defines qué usuarios y con qué contraseña visible quieres dejarlos
    usuarios = [
        ("organizador1", "123456"),  # usuario, nueva contraseña en texto plano
        ("organizador2", "123456"),
    ]

    for username, plain in usuarios:
        hashed = hash_password(plain)
        print(f"Actualizando {username} -> {hashed}")

        res = (
            supabase.table("usuarios")
            .update({"password": hashed})
            .eq("username", username)
            .execute()
        )

        print("Respuesta Supabase:", res.data)

    print("Listo. Ya puedes borrar este script si quieres.")

if __name__ == "__main__":
    main()
