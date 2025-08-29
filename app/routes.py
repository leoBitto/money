from flask import render_template, Blueprint
import pandas as pd

bp = Blueprint("main", __name__)

@bp.route("/")
def index():
    # Dati mock
    df = pd.DataFrame({
        "date": pd.date_range(end=pd.Timestamp.today(), periods=10),
        "price": range(100, 110)
    })
    return render_template("index.html", data=df.to_dict(orient="records"))
