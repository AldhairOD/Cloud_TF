import os
from datetime import date

import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv
import bcrypt  # para comparar contraseñas encriptadas
import pandas as pd
from io import BytesIO

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
# Helpers de caché (Organización y Facultades)
# ==========================
@st.cache_data
def get_organizaciones():
    try:
        res = supabase.table("modelos_negocio").select("id,nombre").execute()
        return res.data or []
    except Exception:
        return []


@st.cache_data
def get_organizaciones_dict():
    orgs = get_organizaciones()
    return {o["id"]: o["nombre"] for o in orgs}


@st.cache_data
def get_facultades_all():
    try:
        res = supabase.table("facultades").select("id,nombre,modelo_negocio_id").execute()
        return res.data or []
    except Exception:
        return []


@st.cache_data
def get_facultades_dict():
    facs = get_facultades_all()
    return {f["id"]: f["nombre"] for f in facs}


@st.cache_data
def get_facultades_por_org(org_id: int):
    facs = get_facultades_all()
    return [f for f in facs if f["modelo_negocio_id"] == org_id]


# ==========================
# Manejo de sesión
# ==========================
def init_session():
    if "perfil" not in st.session_state:
        st.session_state.perfil = None
    if "evento_edit" not in st.session_state:
        st.session_state.evento_edit = None


# ==========================
# LOGIN contra public.usuarios (bcrypt)
# ==========================
def login_view():
    st.title("🎫 Gestión de Eventos - Login")

    st.write("Ingresa con tu usuario y contraseña para gestionar o ver eventos.")

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar", use_container_width=True):
        if not username or not password:
            st.error("Completa usuario y contraseña.")
            return

        try:
            # Buscamos SOLO por username
            res = (
                supabase.table("usuarios")
                .select("*, roles(nombre)")
                .eq("username", username)
                .execute()
            )

            if not res.data:
                st.error("Usuario no encontrado.")
                return

            user_row = res.data[0]
            stored_hash = user_row.get("password")

            if not stored_hash:
                st.error("El usuario no tiene contraseña configurada.")
                return

            # Comparar contraseña ingresada vs hash almacenado
            if not bcrypt.checkpw(
                password.encode("utf-8"),
                stored_hash.encode("utf-8")
            ):
                st.error("Contraseña incorrecta.")
                return

            # Si llegó hasta aquí, login OK
            perfil = user_row
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
    Devuelve la lista de eventos ACTIVO a los que un organizador tiene acceso:
      - Eventos que él creó (usuario_creador_id)
      - Eventos donde está enrolado en eventos_organizadores
    """
    # Eventos creados por el usuario
    r1 = (
        supabase.table("eventos")
        .select("*")
        .eq("usuario_creador_id", usuario_id)
        .eq("estado", "ACTIVO")
        .execute()
    )

    # Eventos donde está enrolado
    r2 = (
        supabase.table("eventos")
        .select("*, eventos_organizadores!inner(usuario_id)")
        .eq("eventos_organizadores.usuario_id", usuario_id)
        .eq("estado", "ACTIVO")
        .execute()
    )

    eventos = {}
    for e in r1.data:
        eventos[e["id"]] = e
    for e in r2.data:
        eventos[e["id"]] = e

    return list(eventos.values())


def crear_evento_form(usuario_id: int):
    st.subheader("➕ Crear nuevo evento")

    with st.container(border=True):
        nombre = st.text_input("Nombre del evento")
        fecha_evento = st.date_input("Fecha del evento", value=date.today())

        # Organización (modelo de negocio)
        orgs = get_organizaciones()
        if orgs:
            org_map = {o["nombre"]: o["id"] for o in orgs}
            org_label = st.selectbox(
                "Organización",
                list(org_map.keys()),
                key="org_crear"
            )
            org_id = org_map[org_label]

            # Facultades de esa organización (opcional)
            facs = get_facultades_por_org(org_id)
            fac_options = ["Sin facultad"]
            fac_map = {"Sin facultad": None}
            for f in facs:
                fac_options.append(f["nombre"])
                fac_map[f["nombre"]] = f["id"]

            fac_label = st.selectbox(
                "Facultad (opcional)",
                fac_options,
                key="fac_crear"
            )
            facultad_id = fac_map[fac_label]
        else:
            st.info("No hay organizaciones configuradas todavía.")
            org_id = None
            facultad_id = None

        limite = st.number_input(
            "Límite de asistentes (0 = ilimitado)",
            min_value=0,
            step=1,
            value=0,
        )

        st.caption(
            "La organización es el modelo de negocio (Universidad, Universidad extranjera, etc.). "
            "La facultad es opcional."
        )

        if st.button("Guardar evento", use_container_width=True):
            if not nombre:
                st.error("El nombre del evento es obligatorio.")
                return

            data = {
                "nombre": nombre,
                "fecha_evento": str(fecha_evento),
                "usuario_creador_id": usuario_id,
                "limite_asistentes": None if limite == 0 else int(limite),
                "modelo_negocio_id": org_id,
                "facultad_id": facultad_id,
                "estado": "ACTIVO",
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
    st.subheader("📋 Lista de eventos")

    org_dict = get_organizaciones_dict()
    fac_dict = get_facultades_dict()

    try:
        if es_organizador:
            eventos = get_eventos_para_organizador(usuario_id)
        else:
            eventos = (
                supabase.table("eventos")
                .select("*")
                .eq("estado", "ACTIVO")
                .execute()
                .data
            )
    except Exception as e:
        st.error(f"Error al obtener eventos: {e}")
        return

    if not eventos:
        st.info("No hay eventos para mostrar.")
        return

    for ev in eventos:
        with st.container(border=True):
            st.markdown(f"### {ev['nombre']}")
            st.write(f"📅 **Fecha:** {ev['fecha_evento']}")

            limite = ev["limite_asistentes"]
            if limite is None:
                st.write("👥 **Límite asistentes:** Ilimitado")
            else:
                st.write(f"👥 **Límite asistentes:** {limite}")

            org_name = org_dict.get(ev.get("modelo_negocio_id"))
            fac_name = fac_dict.get(ev.get("facultad_id"))

            if org_name:
                st.write(f"🏢 **Organización:** {org_name}")
            if fac_name:
                st.write(f"🏫 **Facultad:** {fac_name}")
            else:
                st.write("🏫 **Facultad:** Sin facultad")

            st.caption(f"ID evento: {ev['id']}")

            if es_organizador:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✏️ Editar #{ev['id']}", key=f"edit_{ev['id']}"):
                        st.session_state.evento_edit = ev
                with col2:
                    if st.button(f"🗑️ Eliminar #{ev['id']}", key=f"del_{ev['id']}"):
                        try:
                            # Eliminación lógica: estado = INACTIVO
                            supabase.table("eventos").update(
                                {"estado": "INACTIVO"}
                            ).eq("id", ev["id"]).execute()
                            st.success("Evento desactivado (eliminación lógica).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al desactivar evento: {e}")


def editar_evento_view():
    ev = st.session_state.evento_edit
    if not ev:
        return

    st.subheader(f"✏️ Editar evento #{ev['id']}")

    try:
        fecha_val = date.fromisoformat(ev["fecha_evento"])
    except Exception:
        fecha_val = ev["fecha_evento"]

    org_dict = get_organizaciones_dict()
    fac_all = get_facultades_all()

    with st.container(border=True):
        nombre = st.text_input("Nombre del evento", value=ev["nombre"])
        fecha_evento = st.date_input("Fecha del evento", value=fecha_val)
        limite_actual = ev["limite_asistentes"] if ev["limite_asistentes"] is not None else 0
        limite = st.number_input(
            "Límite de asistentes (0 = ilimitado)",
            min_value=0,
            step=1,
            value=limite_actual,
        )

        # Organización actual
        org_id_actual = ev.get("modelo_negocio_id")
        orgs = get_organizaciones()
        org_options = [o["nombre"] for o in orgs]
        org_map = {o["nombre"]: o["id"] for o in orgs}
        if org_id_actual:
            org_label_default = org_dict.get(org_id_actual)
        else:
            org_label_default = org_options[0] if org_options else None

        if org_options and org_label_default:
            org_label = st.selectbox(
                "Organización",
                org_options,
                index=org_options.index(org_label_default),
                key="org_editar"
            )
            org_id = org_map[org_label]
        elif org_options:
            org_label = st.selectbox("Organización", org_options, key="org_editar")
            org_id = org_map[org_label]
        else:
            st.info("No hay organizaciones configuradas.")
            org_id = None

        # Facultades para la organización seleccionada
        facs_org = get_facultades_por_org(org_id) if org_id else []
        fac_options = ["Sin facultad"]
        fac_map = {"Sin facultad": None}
        for f in facs_org:
            fac_options.append(f["nombre"])
            fac_map[f["nombre"]] = f["id"]

        fac_id_actual = ev.get("facultad_id")
        fac_name_actual = None
        if fac_id_actual:
            fac_name_actual = next((f["nombre"] for f in fac_all if f["id"] == fac_id_actual), None)

        if fac_name_actual and fac_name_actual in fac_options:
            fac_label = st.selectbox(
                "Facultad (opcional)",
                fac_options,
                index=fac_options.index(fac_name_actual),
                key="fac_editar"
            )
        else:
            fac_label = st.selectbox(
                "Facultad (opcional)",
                fac_options,
                key="fac_editar"
            )

        facultad_id = fac_map[fac_label]

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Guardar cambios", use_container_width=True):
                data = {
                    "nombre": nombre,
                    "fecha_evento": str(fecha_evento),
                    "limite_asistentes": None if limite == 0 else int(limite),
                    "modelo_negocio_id": org_id,
                    "facultad_id": facultad_id,
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
            if st.button("Cancelar", use_container_width=True):
                st.session_state.evento_edit = None
                st.rerun()


# ==========================
# Enrolar organizadores a eventos
# ==========================
def enrolar_organizador_view():
    st.subheader("👥 Enrolar organizadores a un evento")

    try:
        # Solo eventos ACTIVO
        eventos = (
            supabase.table("eventos")
            .select("id,nombre,usuario_creador_id")
            .eq("estado", "ACTIVO")
            .execute()
            .data
        )
    except Exception as e:
        st.error(f"Error al obtener eventos: {e}")
        return

    if not eventos:
        st.info("No hay eventos disponibles.")
        return

    mapa_eventos = {f"{e['nombre']} (#{e['id']})": e for e in eventos}
    evento_label = st.selectbox(
        "Selecciona evento",
        list(mapa_eventos.keys()),
        key="evento_enrolar"
    )
    evento = mapa_eventos[evento_label]
    evento_id = evento["id"]
    creador_id = evento["usuario_creador_id"]

    # Organizadores enrolados actualmente
    try:
        enrolados_res = (
            supabase.table("eventos_organizadores")
            .select("usuario_id")
            .eq("evento_id", evento_id)
            .execute()
        )
        enrolados_ids = {row["usuario_id"] for row in enrolados_res.data}
    except Exception:
        enrolados_ids = set()

    # Traemos solo los ORGANIZADORES (rol_id = 2 -> ajusta si tu id es otro)
    try:
        ORG_ROLE_ID = 2
        orgs_res = (
            supabase.table("usuarios")
            .select("id, username, rol_id")
            .eq("rol_id", ORG_ROLE_ID)
            .execute()
        )
        orgs = orgs_res.data or []
    except Exception as e:
        st.error(f"Error al obtener organizadores: {e}")
        return

    enrolados_nombres = [o["username"] for o in orgs if o["id"] in enrolados_ids]
    st.write("Organizador principal (creador): ", f"**id {creador_id}**")
    if enrolados_nombres:
        st.write("Organizadores ya enrolados:", ", ".join(enrolados_nombres))
    else:
        st.write("Aún no hay organizadores adicionales enrolados.")

    # Filtrar candidatos: NO creador, NO ya enrolados
    candidatos = [
        o for o in orgs if o["id"] != creador_id and o["id"] not in enrolados_ids
    ]

    if not candidatos:
        st.info("Ya no hay más organizadores disponibles para enrolar en este evento.")
        return

    mapa_orgs = {
        f"{o['username']} (id {o['id']})": o["id"] for o in candidatos
    }

    org_label = st.selectbox("Selecciona organizador", list(mapa_orgs.keys()))

    if st.button("Enrolar organizador", use_container_width=True):
        data = {
            "evento_id": evento_id,
            "usuario_id": mapa_orgs[org_label],
        }
        try:
            supabase.table("eventos_organizadores").upsert(data).execute()
            st.success("Organizador enrolado al evento.")
            st.rerun()
        except Exception as e:
            st.error(f"Error al enrolar organizador: {e}")


# ==========================
# Dashboard general (organizador) + exportar Excel
# ==========================
def dashboard_view(usuario_id: int):
    st.subheader("📊 Dashboard general de eventos")

    eventos = get_eventos_para_organizador(usuario_id)
    if not eventos:
        st.info("No tienes eventos activos para mostrar en el dashboard.")
        return

    eventos_dict = {e["id"]: e for e in eventos}
    eventos_ids = list(eventos_dict.keys())

    # Traer registros de asistencia/registro de esos eventos
    try:
        res_asist = (
            supabase.table("eventos_asistentes")
            .select("evento_id, usuario_id, registrado_en, estado")
            .in_("evento_id", eventos_ids)
            .execute()
        )
        registros = res_asist.data or []
    except Exception as e:
        registros = []
        st.error(f"Error al obtener datos de eventos_asistentes para el dashboard: {e}")
        return

    total_eventos = len(eventos)
    total_registros = len(registros)
    total_asistidos = sum(1 for r in registros if r.get("estado") == "ASISTIDO")

    col1, col2, col3 = st.columns(3)
    col1.metric("Eventos activos", total_eventos)
    col2.metric("Registros totales", total_registros)
    col3.metric("Asistencias totales", total_asistidos)

    # Agregar resumen por evento
    resumen = {}
    for e_id in eventos_ids:
        resumen[e_id] = {"registrados": 0, "asistidos": 0}

    for r in registros:
        e_id = r["evento_id"]
        if e_id not in resumen:
            resumen[e_id] = {"registrados": 0, "asistidos": 0}
        if r.get("estado") == "ASISTIDO":
            resumen[e_id]["asistidos"] += 1
        else:
            resumen[e_id]["registrados"] += 1

    filas_resumen = []
    for e_id, data in resumen.items():
        ev = eventos_dict.get(e_id, {})
        filas_resumen.append(
            {
                "Evento": ev.get("nombre", f"Evento {e_id}"),
                "Registrados": data["registrados"],
                "Asistidos": data["asistidos"],
            }
        )

    df_resumen = pd.DataFrame(filas_resumen)

    st.markdown("### 📌 Resumen por evento")
    st.dataframe(df_resumen, use_container_width=True)

    if not df_resumen.empty:
        # Gráfico simple de asistentes por evento
        chart_df = df_resumen.set_index("Evento")[["Registrados", "Asistidos"]]
        st.bar_chart(chart_df)

    # ============ Exportar a Excel ============
    st.markdown("### 📥 Exportar detalle a Excel")

    if not registros:
        st.info("No hay registros para exportar.")
        return

    # Traer datos de usuarios para enriquecer el Excel
    user_ids = list({r["usuario_id"] for r in registros})
    try:
        res_users = (
            supabase.table("usuarios")
            .select("id, username, nombres, apellidos, correo")
            .in_("id", user_ids)
            .execute()
        )
        usuarios_rows = res_users.data or []
    except Exception as e:
        usuarios_rows = []
        st.error(f"Error al obtener usuarios para el Excel: {e}")
        return

    usuarios_dict = {u["id"]: u for u in usuarios_rows}

    filas_excel = []
    for r in registros:
        ev = eventos_dict.get(r["evento_id"], {})
        u = usuarios_dict.get(r["usuario_id"], {})

        filas_excel.append(
            {
                "ID evento": r["evento_id"],
                "Nombre evento": ev.get("nombre", ""),
                "Fecha evento": ev.get("fecha_evento", ""),
                "ID usuario": r["usuario_id"],
                "Username": u.get("username", ""),
                "Nombre completo": f"{u.get('nombres','')} {u.get('apellidos','')}".strip(),
                "Correo": u.get("correo", ""),
                "Estado": r.get("estado", ""),
                "Registrado en": r.get("registrado_en", ""),
            }
        )

    df_excel = pd.DataFrame(filas_excel)

    buffer = BytesIO()
    df_excel.to_excel(buffer, index=False)
    buffer.seek(0)

    st.download_button(
        label="Descargar reporte completo en Excel",
        data=buffer,
        file_name="reporte_eventos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ==========================
# Ver alumnos registrados / asistentes (eventos_asistentes)
# ==========================
def inscripciones_asistencia_view(usuario_id: int):
    st.subheader("👨‍🎓 Inscripciones y asistencia")

    # Eventos activos donde el organizador tiene acceso
    eventos = get_eventos_para_organizador(usuario_id)
    if not eventos:
        st.info("No tienes eventos activos para revisar.")
        return

    mapa_eventos = {f"{e['nombre']} (#{e['id']})": e["id"] for e in eventos}
    evento_label = st.selectbox(
        "Selecciona evento",
        list(mapa_eventos.keys()),
        key="evento_inscripciones"
    )
    evento_id = mapa_eventos[evento_label]

    st.markdown(f"### Evento seleccionado: {evento_label}")

    try:
        res = (
            supabase.table("eventos_asistentes")
            .select(
                "evento_id, usuario_id, registrado_en, estado, "
                "usuarios(nombres,apellidos,correo,username)"
            )
            .eq("evento_id", evento_id)
            .execute()
        )
        registros = res.data or []
    except Exception as e:
        registros = []
        st.error(f"Error al obtener datos de eventos_asistentes: {e}")

    registrados = []
    asistidos = []

    for r in registros:
        u = r.get("usuarios") or {}
        nombre_completo = f"{u.get('nombres','')} {u.get('apellidos','')}".strip()
        fila = {
            "ID usuario": r["usuario_id"],
            "Username": u.get("username", ""),
            "Nombre": nombre_completo,
            "Correo": u.get("correo", ""),
            "Registrado en": r.get("registrado_en", ""),
            "Estado": r.get("estado", ""),
        }

        if r.get("estado") == "ASISTIDO":
            asistidos.append(fila)
        else:
            registrados.append(fila)

    st.markdown("### 📝 Estudiantes registrados (no asistidos)")
    if registrados:
        st.table(registrados)
    else:
        st.info("No hay estudiantes solo registrados para este evento.")

    st.markdown("### ✅ Estudiantes que asistieron")
    if asistidos:
        st.table(asistidos)
    else:
        st.info("No hay estudiantes marcados como asistentes para este evento.")


# ==========================
# Pantalla principal
# ==========================
def main_app():
    perfil = st.session_state.perfil
    rol_nombre = perfil["roles"]["nombre"]

    st.sidebar.title("Menú")
    st.sidebar.write(f"👤 Usuario: **{perfil['username']}**")
    st.sidebar.write(f"🎭 Rol: **{rol_nombre}**")

    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        st.session_state.perfil = None
        st.session_state.evento_edit = None
        st.rerun()

    st.title("🎫 Sistema de Gestión de Eventos")

    es_organizador = (rol_nombre == "ORGANIZADOR")

    if es_organizador:
        pestañas = st.tabs([
            "Dashboard",
            "Mis eventos",
            "Enrolar organizadores",
            "Inscripciones y asistencia"
        ])
        with pestañas[0]:
            dashboard_view(perfil["id"])
        with pestañas[1]:
            crear_evento_form(perfil["id"])
            st.divider()
            lista_eventos_view(perfil["id"], es_organizador=True)
            editar_evento_view()
        with pestañas[2]:
            enrolar_organizador_view()
        with pestañas[3]:
            inscripciones_asistencia_view(perfil["id"])
    else:
        st.header("Vista estudiante")
        st.write("Aquí puedes ver los eventos disponibles.")
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
