import os
from datetime import date

import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv

# ==========================
# Cargar variables de entorno
# ==========================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Faltan las variables SUPABASE_URL o SUPABASE_KEY en el .env")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================
# Manejo de sesión
# ==========================
def init_session():
    if "perfil" not in st.session_state:
        st.session_state.perfil = None
    if "evento_edit" not in st.session_state:
        st.session_state.evento_edit = None


# ==========================
# LOGIN contra public.usuarios
# ==========================
def login_view():
    st.title("Gestión de Eventos - Login")

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):
        if not username or not password:
            st.error("Completa usuario y contraseña.")
            return

        try:
            # Buscamos en la tabla usuarios + rol asociado
            res = (
                supabase.table("usuarios")
                .select("*, roles(nombre)")
                .eq("username", username)
                .eq("password", password)
                .execute()
            )

            if not res.data:
                st.error("Credenciales inválidas.")
                return

            perfil = res.data[0]
            st.session_state.perfil = perfil
            st.success("Inicio de sesión correcto.")
            st.rerun()

        except Exception as e:
            st.error(f"Error al intentar iniciar sesión: {e}")


# ==========================
# Funciones de eventos
# ==========================
def get_eventos_para_organizador(usuario_id: int):
    """
    Devuelve la lista de eventos a los que un organizador tiene acceso:
      - Eventos que él creó (usuario_creador_id)
      - Eventos donde está enrolado en eventos_organizadores
    """
    # Eventos creados por el usuario
    r1 = (
        supabase.table("eventos")
        .select("*")
        .eq("usuario_creador_id", usuario_id)
        .execute()
    )

    # Eventos donde está enrolado
    r2 = (
        supabase.table("eventos")
        .select("*, eventos_organizadores!inner(usuario_id)")
        .eq("eventos_organizadores.usuario_id", usuario_id)
        .execute()
    )

    eventos = {}
    for e in r1.data:
        eventos[e["id"]] = e
    for e in r2.data:
        eventos[e["id"]] = e

    return list(eventos.values())


def crear_evento_form(usuario_id: int):
    st.subheader("Crear nuevo evento")

    nombre = st.text_input("Nombre del evento")
    fecha_evento = st.date_input("Fecha del evento", value=date.today())
    limite = st.number_input(
        "Límite de asistentes (0 = ilimitado)",
        min_value=0,
        step=1,
        value=0,
    )

    if st.button("Guardar evento"):
        if not nombre:
            st.error("El nombre del evento es obligatorio.")
            return

        data = {
            "nombre": nombre,
            "fecha_evento": str(fecha_evento),
            "usuario_creador_id": usuario_id,
            "limite_asistentes": None if limite == 0 else int(limite),
        }

        try:
            res = supabase.table("eventos").insert(data).execute()
            if res.data:
                st.success("Evento creado correctamente.")
                st.rerun()
            else:
                st.error("No se pudo crear el evento.")
        except Exception as e:
            st.error(f"Error al crear evento: {e}")


def lista_eventos_view(usuario_id: int, es_organizador: bool):
    st.subheader("Eventos")

    try:
        if es_organizador:
            eventos = get_eventos_para_organizador(usuario_id)
        else:
            # Por ahora, el estudiante ve todos los eventos
            eventos = supabase.table("eventos").select("*").execute().data
    except Exception as e:
        st.error(f"Error al obtener eventos: {e}")
        return

    if not eventos:
        st.info("No hay eventos para mostrar.")
        return

    for ev in eventos:
        with st.container():
            st.markdown(f"**{ev['nombre']}**")
            st.write(f"Fecha: {ev['fecha_evento']}")
            st.write(f"Límite asistentes: {ev['limite_asistentes']}")
            st.write(f"ID evento: {ev['id']}")

            if es_organizador:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Editar #{ev['id']}", key=f"edit_{ev['id']}"):
                        st.session_state.evento_edit = ev
                with col2:
                    if st.button(f"Eliminar #{ev['id']}", key=f"del_{ev['id']}"):
                        try:
                            supabase.table("eventos").delete().eq("id", ev["id"]).execute()
                            st.success("Evento eliminado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar evento: {e}")

        st.divider()


def editar_evento_view():
    ev = st.session_state.evento_edit
    if not ev:
        return

    st.subheader(f"Editar evento #{ev['id']} - {ev['nombre']}")

    # fecha_evento viene como string tipo '2025-01-01'
    try:
        fecha_val = date.fromisoformat(ev["fecha_evento"])
    except Exception:
        # por si viene ya como date
        fecha_val = ev["fecha_evento"]

    nombre = st.text_input("Nombre del evento", value=ev["nombre"])
    fecha_evento = st.date_input("Fecha del evento", value=fecha_val)
    limite_actual = ev["limite_asistentes"] if ev["limite_asistentes"] is not None else 0
    limite = st.number_input(
        "Límite de asistentes (0 = ilimitado)",
        min_value=0,
        step=1,
        value=limite_actual,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Guardar cambios"):
            data = {
                "nombre": nombre,
                "fecha_evento": str(fecha_evento),
                "limite_asistentes": None if limite == 0 else int(limite),
                "actualizado_en": "now()",
            }
            try:
                supabase.table("eventos").update(data).eq("id", ev["id"]).execute()
                st.success("Evento actualizado.")
                st.session_state.evento_edit = None
                st.rerun()
            except Exception as e:
                st.error(f"Error al actualizar evento: {e}")

    with col2:
        if st.button("Cancelar edición"):
            st.session_state.evento_edit = None
            st.rerun()


def enrolar_organizador_view():
    st.subheader("Enrolar organizador a evento")

    try:
        eventos = supabase.table("eventos").select("id,nombre").execute().data
        orgs = (
            supabase.table("usuarios")
            .select("id,username, rol_id, roles(nombre)")
            .eq("roles.nombre", "ORGANIZADOR")
            .execute()
            .data
        )
    except Exception as e:
        st.error(f"Error al obtener datos para enrolar: {e}")
        return

    if not eventos:
        st.info("No hay eventos disponibles.")
        return
    if not orgs:
        st.info("No hay organizadores disponibles.")
        return

    mapa_eventos = {f"{e['nombre']} (#{e['id']})": e["id"] for e in eventos}
    mapa_orgs = {f"{o['username']} (id {o['id']})": o["id"] for o in orgs}

    evento_label = st.selectbox("Selecciona evento", list(mapa_eventos.keys()))
    org_label = st.selectbox("Selecciona organizador", list(mapa_orgs.keys()))

    if st.button("Enrolar"):
        data = {
            "evento_id": mapa_eventos[evento_label],
            "usuario_id": mapa_orgs[org_label],
        }
        try:
            supabase.table("eventos_organizadores").upsert(data).execute()
            st.success("Organizador enrolado al evento.")
        except Exception as e:
            st.error(f"Error al enrolar organizador: {e}")


# ==========================
# Pantalla principal
# ==========================
def main_app():
    perfil = st.session_state.perfil
    rol_nombre = perfil["roles"]["nombre"]

    st.sidebar.title("Menú")
    st.sidebar.write(f"Usuario: **{perfil['username']}**")
    st.sidebar.write(f"Rol: **{rol_nombre}**")

    if st.sidebar.button("Cerrar sesión"):
        st.session_state.perfil = None
        st.session_state.evento_edit = None
        st.rerun()

    st.title("Sistema de Gestión de Eventos")

    es_organizador = (rol_nombre == "ORGANIZADOR")

    if es_organizador:
        st.header("Organizador")
        crear_evento_form(perfil["id"])
        st.divider()
        lista_eventos_view(perfil["id"], es_organizador=True)
        editar_evento_view()
        st.divider()
        enrolar_organizador_view()
    else:
        st.header("Estudiante")
        lista_eventos_view(perfil["id"], es_organizador=False)


# ==========================
# Punto de entrada
# ==========================
def main():
    init_session()

    if st.session_state.perfil is None:
        login_view()
    else:
        main_app()


if __name__ == "__main__":
    main()
