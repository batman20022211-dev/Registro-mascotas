import base64
import hmac
import os
import re
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "static", "i")           # galería fija (1.jpg, 2.jpg…)
EXTENSIONES = {"png", "jpg", "jpeg", "gif", "webp"}
TIPOS_IMAGEN = ("image/png", "image/jpeg", "image/gif", "image/webp")
MAX_FOTO_BYTES = 2 * 1024 * 1024  # 2 MB por imagen

# Contraseña del administrador. Puedes cambiarla con la variable de entorno ADMIN_PASSWORD.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "123abc")

# Estados de una mascota
PENDIENTE = "pendiente"   # esperando validación del administrador
APROBADA = "aprobada"     # visible en adopción
RECHAZADA = "rechazada"   # no aparece en adopción
ADOPTADA = "adoptada"     # ya adoptada: desaparece de adopción
ESTADOS = [PENDIENTE, APROBADA, RECHAZADA, ADOPTADA]
ESTADO_TEXTO = {
    PENDIENTE: "En revisión",
    APROBADA: "Publicada",
    RECHAZADA: "Rechazada",
    ADOPTADA: "Adoptada",
}

ESPECIES = ["Perro", "Gato", "Cuyo", "Hámster", "Conejo", "Periquito", "Otro"]
VACUNAS = ["Rabia", "Parvovirus", "Moquillo", "Triple felina", "Desparasitación", "Otra", "Ninguna"]
EMOJIS = {
    "Perro": "🐶", "Gato": "🐱", "Cuyo": "🐹", "Hámster": "🐹",
    "Conejo": "🐰", "Periquito": "🦜", "Otro": "🐾",
}

CAMPOS_REGISTRO = {
    "nombre": "Nombre",
    "especie": "Especie",
    "raza": "Raza",
    "edad": "Edad",
    "sexo": "Sexo",
    "color": "Color",
    "peso": "Peso",
    "dueno": "Nombre del dueño",
    "telefono": "Teléfono",
    "notas": "Notas",
    "en_adopcion": "Disponible para adopción",
}

CAMPOS_ADOPCION = {
    "nombre": "Nombre completo",
    "edad": "Edad",
    "telefono": "Teléfono",
    "correo": "Correo",
    "direccion": "Dirección",
    "ocupacion": "Ocupación",
    "vivienda": "Tipo de vivienda",
    "otras_mascotas": "¿Tienes otras mascotas?",
    "experiencia": "Experiencia",
    "motivo": "Motivo",
    "compromiso": "Compromiso de cuidado",
}

# Mascotas de ejemplo: se cargan una sola vez, al crear la base de datos.
SEMILLA_ADOPCION = [
    {"nombre": "gato", "especie": "Gato", "raza": "Siamés", "edad": "2",
     "sexo": "Hembra", "color": "Crema", "peso": "4", "vacunas": ["Triple felina", "Rabia"],
     "notas": "Muy cariñosa, ideal para departamento."},
    {"nombre": "perro", "especie": "Perro", "raza": "Mestizo", "edad": "4",
     "sexo": "Macho", "color": "Café", "peso": "12",
     "vacunas": ["Rabia", "Parvovirus", "Moquillo"],
     "notas": "Juguetón, se lleva bien con niños."},
    {"nombre": "coso", "especie": "Cuyo", "raza": "Peruano", "edad": "1",
     "sexo": "Macho", "color": "Blanco y café", "peso": "1", "vacunas": ["Ninguna"],
     "notas": "Tranquilo y comelón."},
    {"nombre": "coso2", "especie": "Conejo", "raza": "Holandés", "edad": "1",
     "sexo": "Hembra", "color": "Blanco", "peso": "2", "vacunas": ["Desparasitación"],
     "notas": "Le gusta la compañía."},
    {"nombre": "perro2", "especie": "Perro", "raza": "Chihuahua", "edad": "3",
     "sexo": "Hembra", "color": "Café claro", "peso": "3",
     "vacunas": ["Rabia", "Parvovirus"],
     "notas": "Muy leal y atenta, ideal para departamento."},
    {"nombre": "gato2", "especie": "Gato", "raza": "Atigrado mestizo", "edad": "5",
     "sexo": "Macho", "color": "Naranja", "peso": "5",
     "vacunas": ["Triple felina", "Rabia", "Desparasitación"],
     "notas": "Dormilón y muy casero."},
    {"nombre": "periquito", "especie": "Periquito", "raza": "Común", "edad": "2",
     "sexo": "No sé", "color": "Verde", "peso": "0.1", "vacunas": ["Ninguna"],
     "notas": "Canta todas las mañanas."},
    {"nombre": "perro3", "especie": "Perro", "raza": "Labrador mestizo", "edad": "2",
     "sexo": "Macho", "color": "Dorado", "peso": "25",
     "vacunas": ["Rabia", "Parvovirus", "Moquillo", "Desparasitación"],
     "notas": "Muy energético, ideal para familias activas."},
    {"nombre": "gato3", "especie": "Gato", "raza": "Persa", "edad": "7",
     "sexo": "Hembra", "color": "Blanco", "peso": "4.5",
     "vacunas": ["Triple felina", "Rabia"],
     "notas": "Tranquila, necesita cepillado diario."},
    {"nombre": "hamster2", "especie": "Hámster", "raza": "Sirio", "edad": "1",
     "sexo": "Macho", "color": "Dorado", "peso": "0.1", "vacunas": ["Ninguna"],
     "notas": "Nocturno, le encanta correr en la rueda."},
]


def url_base_datos():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///" + os.path.join(BASE_DIR, "formularios.db")
    # Neon entrega URLs que empiezan con "postgresql://"; SQLAlchemy necesita el driver indicado.
    for prefijo in ("postgresql://", "postgres://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-12984787658734hufyyhufj-fjdhfujsdhjajka")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SQLALCHEMY_DATABASE_URI"] = url_base_datos()
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}
app.jinja_env.globals["emoji"] = lambda especie: EMOJIS.get(especie, "🐾")
app.jinja_env.globals["estado_texto"] = lambda estado: ESTADO_TEXTO.get(estado, estado)
app.jinja_env.globals["src_foto"] = lambda foto: (
    "" if not foto else foto if foto.startswith("data:") else url_for("static", filename=foto)
)

db = SQLAlchemy(app)


# ---------- Modelos ----------

class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    correo = db.Column(db.String(160), unique=True, nullable=False)
    contrasena_hash = db.Column(db.String(255), nullable=False)
    creado = db.Column(db.DateTime, server_default=db.func.now())

    # al borrar un usuario sus mascotas se conservan (sin dueño); sus solicitudes se borran
    mascotas = db.relationship("Mascota", back_populates="usuario")
    solicitudes = db.relationship("SolicitudAdopcion", back_populates="usuario", cascade="all, delete-orphan")


class Mascota(db.Model):
    __tablename__ = "mascotas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)  # NULL = mascota de ejemplo
    nombre = db.Column(db.String(120), nullable=False)
    especie = db.Column(db.String(40), nullable=False)
    raza = db.Column(db.String(120), nullable=False)
    edad = db.Column(db.String(10), nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    color = db.Column(db.String(60), nullable=False)
    peso = db.Column(db.String(10), nullable=False)
    vacunas = db.Column(db.JSON, nullable=False, default=list)
    dueno = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    notas = db.Column(db.Text, nullable=False)
    en_adopcion = db.Column(db.Boolean, nullable=False, default=True)
    foto = db.Column(db.Text, nullable=True)  # data URI en base64 ("data:image/jpeg;base64,...") o "i/1.jpg" (ejemplo)
    estado = db.Column(db.String(20), nullable=False, default=PENDIENTE)
    creada = db.Column(db.DateTime, server_default=db.func.now())

    usuario = db.relationship("Usuario", back_populates="mascotas")
    solicitudes = db.relationship(
        "SolicitudAdopcion", back_populates="mascota", cascade="all, delete-orphan"
    )


class SolicitudAdopcion(db.Model):
    __tablename__ = "solicitudes_adopcion"

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    datos = db.Column(db.JSON, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default=PENDIENTE)
    creada = db.Column(db.DateTime, server_default=db.func.now())

    mascota = db.relationship("Mascota", back_populates="solicitudes")
    usuario = db.relationship("Usuario", back_populates="solicitudes")


# ---------- Sesión y permisos ----------

def usuario_actual():
    uid = session.get("usuario_id")
    return db.session.get(Usuario, uid) if uid else None


@app.context_processor
def inyectar_sesion():
    return {"usuario": usuario_actual(), "es_admin": bool(session.get("admin"))}


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is None:
            flash("Inicia sesión o crea una cuenta para continuar.", "error")
            return redirect(url_for("cuenta_login"))
        return vista(*args, **kwargs)
    return envoltura


def admin_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not session.get("admin"):
            flash("Inicia sesión como administrador.", "error")
            return redirect(url_for("admin_login"))
        return vista(*args, **kwargs)
    return envoltura


# ---------- Ayudas ----------

def extension_valida(nombre):
    return "." in nombre and nombre.rsplit(".", 1)[1].lower() in EXTENSIONES


def faltantes(form, campos):
    return [etiqueta for clave, etiqueta in campos.items() if not form.get(clave, "").strip()]


def es_numero(valor):
    try:
        return float(valor) >= 0
    except ValueError:
        return False


def correo_valido(correo):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo) is not None


def imagenes_galeria():
    if not os.path.isdir(IMG_DIR):
        return []
    archivos = [a for a in os.listdir(IMG_DIR) if extension_valida(a)]

    def orden(nombre):
        base = nombre.rsplit(".", 1)[0]
        return (0, int(base), nombre) if base.isdigit() else (1, 0, nombre)

    return sorted(archivos, key=orden)


def foto_a_base64(archivo):
    """Convierte la foto subida en data URI (base64). Devuelve (texto, error)."""
    if archivo.mimetype not in TIPOS_IMAGEN:
        return None, "Solo se permiten imágenes PNG, JPG, GIF o WEBP."
    contenido = archivo.read()
    if len(contenido) > MAX_FOTO_BYTES:
        return None, "Cada foto debe pesar máximo 2 MB."
    datos = base64.b64encode(contenido).decode("ascii")
    return f"data:{archivo.mimetype};base64,{datos}", None


def leer_mascota(form, archivo_foto, foto_obligatoria):
    """Valida el formulario de mascota. Devuelve (datos, error)."""
    faltan = faltantes(form, CAMPOS_REGISTRO)
    vacunas = [v for v in form.getlist("vacunas") if v in VACUNAS]
    if not vacunas:
        faltan.append("Vacunas")
    tiene_foto = bool(archivo_foto and archivo_foto.filename)
    if foto_obligatoria and not tiene_foto:
        faltan.append("Foto")
    if faltan:
        return None, "Completa todos los campos: " + ", ".join(faltan) + "."
    if not (es_numero(form["edad"]) and es_numero(form["peso"])):
        return None, "La edad y el peso deben ser números."

    campos = ("nombre", "especie", "raza", "edad", "sexo", "color",
              "peso", "dueno", "telefono", "notas")
    datos = {campo: form[campo].strip() for campo in campos}
    datos["vacunas"] = vacunas
    datos["en_adopcion"] = form["en_adopcion"] == "sí"
    if tiene_foto:
        datos["foto"], error = foto_a_base64(archivo_foto)
        if error:
            return None, error
    return datos, None


def aplicar_cambios(mascota, datos):
    for campo, valor in datos.items():
        setattr(mascota, campo, valor)


def valores_de(mascota):
    return {
        "nombre": mascota.nombre, "especie": mascota.especie, "raza": mascota.raza,
        "edad": mascota.edad, "sexo": mascota.sexo, "color": mascota.color,
        "peso": mascota.peso, "dueno": mascota.dueno or "", "telefono": mascota.telefono or "",
        "notas": mascota.notas, "vacunas": mascota.vacunas,
        "en_adopcion": "sí" if mascota.en_adopcion else "no",
        "estado": mascota.estado, "foto": mascota.foto,
    }


def render_formulario(**extra):
    contexto = {"especies": ESPECIES, "vacunas": VACUNAS, "estados": ESTADOS, "mostrar_estado": False}
    contexto.update(extra)
    return render_template("formulario_mascota.html", **contexto)


def sembrar_datos():
    for i, datos in enumerate(SEMILLA_ADOPCION, start=1):
        db.session.add(Mascota(**datos, foto=f"i/{i}.jpg", estado=APROBADA, en_adopcion=True))
    db.session.commit()


# ---------- Público ----------

@app.route("/")
def inicio():
    return redirect(url_for("registro"))


@app.route("/mascotas")
def galeria():
    return render_template("mascotas.html", imagenes=imagenes_galeria())


@app.route("/adopcion")
def adopcion():
    mascotas = db.session.scalars(
        db.select(Mascota)
        .where(Mascota.estado == APROBADA, Mascota.en_adopcion.is_(True))
        .order_by(Mascota.id)
    ).all()
    return render_template("adopcion.html", mascotas=mascotas)


@app.route("/adopcion/<int:mascota_id>", methods=["GET", "POST"])
@login_requerido
def adoptar(mascota_id):
    mascota = db.get_or_404(Mascota, mascota_id)
    if mascota.estado != APROBADA or not mascota.en_adopcion:
        flash("Esa mascota no está disponible para adopción.", "error")
        return redirect(url_for("adopcion"))

    usuario = usuario_actual()
    if mascota.usuario_id == usuario.id:
        flash("No puedes adoptar una mascota que tú registraste.", "error")
        return redirect(url_for("adopcion"))

    ya_pidio = db.session.scalar(
        db.select(SolicitudAdopcion.id).where(
            SolicitudAdopcion.mascota_id == mascota.id,
            SolicitudAdopcion.usuario_id == usuario.id,
            SolicitudAdopcion.estado == PENDIENTE,
        )
    ) is not None

    if request.method == "POST":
        if ya_pidio:
            flash("Ya enviaste una solicitud para esta mascota. Espera la respuesta del administrador.", "error")
            return redirect(url_for("adopcion"))

        f = request.form
        faltan = faltantes(f, CAMPOS_ADOPCION)
        if faltan:
            flash("Completa todos los campos: " + ", ".join(faltan) + ".", "error")
            return redirect(url_for("adoptar", mascota_id=mascota_id))
        if not f["edad"].strip().isdigit() or int(f["edad"]) < 18:
            flash("Debes tener al menos 18 años para adoptar.", "error")
            return redirect(url_for("adoptar", mascota_id=mascota_id))

        datos = {campo: f[campo].strip() for campo in CAMPOS_ADOPCION if campo != "compromiso"}
        datos["compromiso"] = "sí"  # el campo es obligatorio, así que llegó marcado
        db.session.add(SolicitudAdopcion(mascota_id=mascota.id, usuario_id=usuario.id, datos=datos))
        db.session.commit()
        flash(f"¡Gracias! Tu solicitud para adoptar a {mascota.nombre} fue enviada. 💖", "ok")
        return redirect(url_for("adopcion"))

    return render_template("adoptar.html", mascota=mascota, ya_pidio=ya_pidio)


# ---------- Cuentas de usuario ----------

@app.route("/cuenta/registro", methods=["GET", "POST"])
def cuenta_registro():
    if request.method == "POST":
        f = request.form
        nombre = f.get("nombre", "").strip()
        correo = f.get("correo", "").strip().lower()
        contrasena = f.get("contrasena", "")
        confirmar = f.get("confirmar", "")

        errores = []
        if not (nombre and correo and contrasena and confirmar):
            errores.append("Completa todos los campos.")
        if len(nombre) > 120 or len(correo) > 160:
            errores.append("El nombre o el correo son demasiado largos.")
        if correo and not correo_valido(correo):
            errores.append("El correo no es válido.")
        if contrasena and len(contrasena) < 6:
            errores.append("La contraseña debe tener al menos 6 caracteres.")
        if contrasena != confirmar:
            errores.append("Las contraseñas no coinciden.")
        if correo and db.session.scalar(db.select(Usuario.id).where(Usuario.correo == correo)):
            errores.append("Ya existe una cuenta con ese correo.")
        if errores:
            flash(" ".join(errores), "error")
            return redirect(url_for("cuenta_registro"))

        usuario = Usuario(nombre=nombre, correo=correo, contrasena_hash=generate_password_hash(contrasena))
        db.session.add(usuario)
        db.session.commit()
        session["usuario_id"] = usuario.id
        flash(f"¡Cuenta creada! Bienvenido/a, {nombre}. 🎉", "ok")
        return redirect(url_for("registro"))

    return render_template("cuenta_registro.html")


@app.route("/cuenta/login", methods=["GET", "POST"])
def cuenta_login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("contrasena", "")
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.correo == correo))
        if usuario and check_password_hash(usuario.contrasena_hash, contrasena):
            session["usuario_id"] = usuario.id
            flash(f"¡Hola, {usuario.nombre}!", "ok")
            return redirect(url_for("registro"))
        flash("Correo o contraseña incorrectos.", "error")
        return redirect(url_for("cuenta_login"))

    return render_template("cuenta_login.html")


@app.route("/cuenta/salir")
def cuenta_salir():
    session.pop("usuario_id", None)
    flash("Cerraste tu sesión.", "ok")
    return redirect(url_for("adopcion"))


# ---------- Registro de mascotas (usuario) ----------

@app.route("/registro", methods=["GET", "POST"])
@login_requerido
def registro():
    if request.method == "POST":
        datos, error = leer_mascota(request.form, request.files.get("foto"), foto_obligatoria=True)
        if error:
            flash(error, "error")
            return redirect(url_for("registro"))

        mascota = Mascota(
            **datos,
            usuario_id=usuario_actual().id,
            estado=PENDIENTE,
        )
        db.session.add(mascota)
        db.session.commit()
        flash(f"¡{mascota.nombre} fue registrado/a! Un administrador la revisará antes de publicarla. 🎉", "ok")
        return redirect(url_for("mis_mascotas"))

    return render_formulario(
        titulo="Registro de mascota",
        accion=url_for("registro"),
        volver=None,
        editando=False,
        valores={"vacunas": [], "en_adopcion": ""},
    )


@app.route("/mis-mascotas")
@login_requerido
def mis_mascotas():
    mascotas = db.session.scalars(
        db.select(Mascota)
        .where(Mascota.usuario_id == usuario_actual().id)
        .order_by(Mascota.id.desc())
    ).all()
    return render_template("mis_mascotas.html", mascotas=mascotas)


@app.route("/mis-mascotas/<int:mascota_id>/editar", methods=["GET", "POST"])
@login_requerido
def editar_mi_mascota(mascota_id):
    mascota = db.get_or_404(Mascota, mascota_id)
    if mascota.usuario_id != usuario_actual().id:
        flash("Solo puedes modificar las mascotas que tú registraste.", "error")
        return redirect(url_for("mis_mascotas"))
    if mascota.estado == ADOPTADA:
        flash("Esta mascota ya fue adoptada y no se puede modificar.", "error")
        return redirect(url_for("mis_mascotas"))

    if request.method == "POST":
        datos, error = leer_mascota(request.form, request.files.get("foto"), foto_obligatoria=False)
        if error:
            flash(error, "error")
            return redirect(url_for("editar_mi_mascota", mascota_id=mascota_id))
        aplicar_cambios(mascota, datos)
        mascota.estado = PENDIENTE  # cualquier cambio vuelve a pasar por el administrador
        db.session.commit()
        flash("Cambios guardados. Quedan en revisión hasta que un administrador los apruebe.", "ok")
        return redirect(url_for("mis_mascotas"))

    return render_formulario(
        titulo="Editar mascota",
        accion=url_for("editar_mi_mascota", mascota_id=mascota_id),
        volver=url_for("mis_mascotas"),
        editando=True,
        valores=valores_de(mascota),
    )


# ---------- Administrador ----------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        clave = request.form.get("clave", "")
        if hmac.compare_digest(clave.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")):
            session["admin"] = True
            flash("Bienvenido, administrador.", "ok")
            return redirect(url_for("admin"))
        flash("Contraseña incorrecta.", "error")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/salir")
def admin_salir():
    session.pop("admin", None)
    flash("Cerraste la sesión de administrador.", "ok")
    return redirect(url_for("adopcion"))


@app.route("/admin")
@admin_requerido
def admin():
    pendientes = db.session.scalars(
        db.select(Mascota).where(Mascota.estado == PENDIENTE).order_by(Mascota.id)
    ).all()
    solicitudes = db.session.scalars(
        db.select(SolicitudAdopcion)
        .where(SolicitudAdopcion.estado == PENDIENTE)
        .order_by(SolicitudAdopcion.id)
    ).all()
    mascotas = db.session.scalars(db.select(Mascota).order_by(Mascota.id.desc())).all()
    usuarios = db.session.scalars(db.select(Usuario).order_by(Usuario.id)).all()
    return render_template(
        "admin.html",
        pendientes=pendientes,
        solicitudes=solicitudes,
        mascotas=mascotas,
        usuarios=usuarios,
        campos_adopcion=CAMPOS_ADOPCION,
    )


@app.route("/admin/mascotas/<int:mascota_id>/editar", methods=["GET", "POST"])
@admin_requerido
def admin_editar_mascota(mascota_id):
    mascota = db.get_or_404(Mascota, mascota_id)

    if request.method == "POST":
        datos, error = leer_mascota(request.form, request.files.get("foto"), foto_obligatoria=False)
        if error:
            flash(error, "error")
            return redirect(url_for("admin_editar_mascota", mascota_id=mascota_id))
        aplicar_cambios(mascota, datos)
        estado = request.form.get("estado")
        if estado in ESTADOS:
            mascota.estado = estado
        db.session.commit()
        flash(f"Cambios de {mascota.nombre} guardados.", "ok")
        return redirect(url_for("admin"))

    return render_formulario(
        titulo=f"Editar a {mascota.nombre}",
        accion=url_for("admin_editar_mascota", mascota_id=mascota_id),
        volver=url_for("admin"),
        editando=True,
        mostrar_estado=True,
        valores=valores_de(mascota),
    )


@app.route("/admin/mascotas/<int:mascota_id>/aprobar", methods=["POST"])
@admin_requerido
def admin_aprobar_mascota(mascota_id):
    mascota = db.get_or_404(Mascota, mascota_id)
    mascota.estado = APROBADA
    db.session.commit()
    flash(f"{mascota.nombre} fue aprobado/a y ya aparece en adopción.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/mascotas/<int:mascota_id>/rechazar", methods=["POST"])
@admin_requerido
def admin_rechazar_mascota(mascota_id):
    mascota = db.get_or_404(Mascota, mascota_id)
    mascota.estado = RECHAZADA
    db.session.commit()
    flash(f"{mascota.nombre} fue rechazado/a y no aparecerá en adopción.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/mascotas/<int:mascota_id>/eliminar", methods=["POST"])
@admin_requerido
def admin_eliminar_mascota(mascota_id):
    mascota = db.get_or_404(Mascota, mascota_id)
    nombre = mascota.nombre
    db.session.delete(mascota)  # también borra sus solicitudes de adopción
    db.session.commit()
    flash(f"{nombre} fue eliminado/a.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/solicitudes/<int:solicitud_id>/aprobar", methods=["POST"])
@admin_requerido
def admin_aprobar_solicitud(solicitud_id):
    solicitud = db.get_or_404(SolicitudAdopcion, solicitud_id)
    if solicitud.estado != PENDIENTE:
        flash("Esta solicitud ya fue revisada.", "error")
        return redirect(url_for("admin"))

    mascota = solicitud.mascota
    solicitud.estado = APROBADA
    mascota.estado = ADOPTADA  # desaparece de la lista de adopción
    for otra in mascota.solicitudes:
        if otra.estado == PENDIENTE and otra.id != solicitud.id:
            otra.estado = RECHAZADA  # ya no hay animal disponible para esas solicitudes
    db.session.commit()
    flash(f"Adopción aprobada: {mascota.nombre} ya no aparece en adopción.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/solicitudes/<int:solicitud_id>/rechazar", methods=["POST"])
@admin_requerido
def admin_rechazar_solicitud(solicitud_id):
    solicitud = db.get_or_404(SolicitudAdopcion, solicitud_id)
    if solicitud.estado != PENDIENTE:
        flash("Esta solicitud ya fue revisada.", "error")
        return redirect(url_for("admin"))

    solicitud.estado = RECHAZADA  # la mascota sigue disponible
    db.session.commit()
    flash(f"Solicitud rechazada. {solicitud.mascota.nombre} sigue en adopción.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/usuarios/<int:usuario_id>/eliminar", methods=["POST"])
@admin_requerido
def admin_eliminar_usuario(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    nombre = usuario.nombre
    db.session.delete(usuario)  # sus mascotas quedan sin dueño y sus solicitudes se borran
    db.session.commit()
    flash(f"La cuenta de {nombre} fue eliminada. Sus mascotas siguen registradas.", "ok")
    return redirect(url_for("admin"))


# ---------- Arranque ----------

with app.app_context():
    tabla_nueva = not inspect(db.engine).has_table("mascotas")
    db.create_all()
    if tabla_nueva:
        sembrar_datos()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
