from flask import Flask, render_template, request, url_for, redirect
import logging
from datetime import datetime, timedelta
from garminconnect import Garmin
import matplotlib.pyplot as plt
import numpy as np
import os
import io
import base64

app = Flask(__name__)

# Logging configuratie
logging.basicConfig(level=logging.INFO)

# Constantes
USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")

@app.route("/", methods=["GET", "POST"])
def index():
    """
    Startpagina met een formulier voor datumselectie en de grafiekweergave.
    """
    graph_url = None
    error = None

    if request.method == "POST":
        # Ophalen van datums uit formulier
        from_date = request.form.get("from_date")
        to_date = request.form.get("to_date")

        if not from_date or not to_date:
            error = "Beide datums moeten worden ingevuld."
        else:
            try:
                # Convert datums naar datetime objecten
                start_date = datetime.strptime(from_date, "%Y-%m-%d")
                end_date = datetime.strptime(to_date, "%Y-%m-%d")

                if start_date > end_date:
                    error = "'From date' mag niet later zijn dan 'To date'."
                else:
                    # Genereer de grafiek
                    graph_url = generate_graph(start_date, end_date)

            except ValueError:
                error = "Ongeldig datumformaat. Gebruik 'YYYY-MM-DD'."
            except Exception as e:
                error = f"Fout bij ophalen van gegevens: {e}"

    return render_template("index.html", graph_url=graph_url, error=error)


def generate_graph(start_date, end_date):
    """
    Genereer de grafiek met hartslagverdeling en een correcte lognormale verdeling.
    """
    # Verbinding met Garmin Connect
    logging.info("Verbinding maken met Garmin Connect...")
    client = Garmin(USERNAME, PASSWORD)
    client.login()
    logging.info("Succesvol ingelogd op Garmin Connect.")

    # Gegevens ophalen binnen de opgegeven datums
    current_date = start_date
    combined_data = []

    while current_date <= end_date:
        cdate = current_date.strftime('%Y-%m-%d')
        try:
            daily_data = client.get_heart_rates(cdate)
            if daily_data and "heartRateValues" in daily_data:
                heart_rate_values = [
                    value[1] for value in daily_data["heartRateValues"] if value[1] is not None
                ]
                combined_data.extend(heart_rate_values)
        except Exception as e:
            logging.error(f"Fout bij ophalen van gegevens voor {cdate}: {e}")
        current_date += timedelta(days=1)

    if not combined_data:
        raise ValueError("Geen gegevens beschikbaar voor de opgegeven periode.")

    # Data voor histogram en lognormale verdeling
    heart_rate_array = np.array(combined_data)
    mean = np.mean(np.log(heart_rate_array))
    std_dev = np.std(np.log(heart_rate_array))

    # Bereken de lognormale verdeling
    x = np.linspace(min(heart_rate_array), max(heart_rate_array), 500)
    pdf = (1 / (x * std_dev * np.sqrt(2 * np.pi))) * np.exp(
        -((np.log(x) - mean) ** 2) / (2 * std_dev ** 2)
    )

    # Histogram omzetten naar percentages
    hist, bins = np.histogram(heart_rate_array, bins=np.arange(40, 200, 10), density=False)
    total_count = sum(hist)
    hist_percentage = (hist / total_count) * 100  # Converteer naar percentages
    bin_centers = (bins[:-1] + bins[1:]) / 2
    pdf_scaled = pdf * max(hist_percentage) / max(pdf)

    # Plot genereren
    plt.figure(figsize=(8, 4))
    plt.bar(bin_centers, hist_percentage, width=8, color="orange", alpha=0.7, label="Histogram (in %)")
    plt.plot(x, pdf_scaled, 'r-', label="Lognormale verdeling")
    plt.xlabel("Hartslag (bpm)")
    plt.ylabel("Percentage (%)")
    plt.title("Hartslagverdeling")
    plt.legend()

    # Opslaan naar een Base64-afbeelding
    img = io.BytesIO()
    plt.savefig(img, format="png")
    img.seek(0)
    img_base64 = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return f"data:image/png;base64,{img_base64}"



@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint om te controleren of de service actief is.
    """
    return {"status": "healthy", "message": "De service is actief en operationeel"}, 200


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
