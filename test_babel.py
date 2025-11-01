from flask import Flask, session, request
from flask_babel import Babel, format_currency, format_decimal

app = Flask(__name__)
app.secret_key = "testkey"
babel = Babel(app)

@babel.localeselector
def get_locale():
    # manually switch language via query ?lang=en or ?lang=pt
    lang = request.args.get("lang")
    if lang in ["en", "pt"]:
        session["lang"] = lang
    return session.get("lang", "en")

@app.route("/")
def index():
    price = 1234.56
    weight = 78.9
    return f"""
    <p>Price: {format_currency(price, 'EUR')}</p>
    <p>Weight: {format_decimal(weight)} kg</p>
    <p>Switch language: <a href='/?lang=en'>English</a> | <a href='/?lang=pt'>Português</a></p>
    """

if __name__ == "__main__":
    app.run(debug=True)
