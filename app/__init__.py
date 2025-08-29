from flask import Flask, render_template
import pandas as pd

def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        df = pd.DataFrame({
            "date": pd.date_range(end=pd.Timestamp.today(), periods=10),
            "price": range(100, 110)
        })
        return render_template("index.html", data=df.to_dict(orient="records"))

    return app
