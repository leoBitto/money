def fmt_number(value, suffix="", decimals=2, default="-"):
    """Formatta un numero con decimali e suffisso, gestendo None."""
    if value is None:
        return default
    try:
        return f"{value:.{decimals}f}{suffix}"
    except Exception:
        return default

def color_class(value, threshold=0, success="text-success", danger="text-danger", default="text-muted"):
    """Restituisce la classe Bootstrap in base al valore e alla soglia."""
    if value is None:
        return default
    return success if value >= threshold else danger

def register_filters(app):
    """Registra i filtri Jinja nell'app Flask."""
    app.jinja_env.filters["fmt_number"] = fmt_number
    app.jinja_env.filters["color_class"] = color_class
