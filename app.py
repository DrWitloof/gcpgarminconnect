from flask import Flask, jsonify
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from garminconnect import Garmin, GarminConnectConnectionError, GarminConnectTooManyRequestsError
import os

app = Flask(__name__)

# Logging configuratie
logging.basicConfig(level=logging.INFO)

# Constantes
HEART_RATE_RANGE_STEP = 10
USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")

def group_heart_rate_data(heart_rate_data):
    """
    Groepeer hartslagmetingen in intervallen van HEART_RATE_RANGE_STEP bpm en sorteer buckets.
    """
    grouped_data = defaultdict(int)
    for entry in heart_rate_data:
        heart_rate = entry.get("heartRate", 0)
        time_in_seconds = entry.get("duration", 0)

        # Creëer een bucket in het formaat "999-999"
        lower_bound = (heart_rate // HEART_RATE_RANGE_STEP) * HEART_RATE_RANGE_STEP
        upper_bound = lower_bound + HEART_RATE_RANGE_STEP - 1
        range_key = f"{lower_bound:03}-{upper_bound:03}"

        grouped_data[range_key] += time_in_seconds

    # Sorteer de buckets op hun numerieke waarde
    sorted_grouped_data = {k: grouped_data[k] for k in sorted(grouped_data)}

    return sorted_grouped_data

def calculate_percentages(grouped_data):
    total_time = sum(grouped_data.values())
    percentages = {
        range_key: (time_in_seconds / total_time) * 100
        for range_key, time_in_seconds in grouped_data.items()
    }
    return total_time, percentages

def get_date_ranges(start_date, weeks):
    date_ranges = []
    for i in range(weeks):
        end_date = start_date - timedelta(days=i * 7)
        start_date = end_date - timedelta(days=6)
        date_ranges.append((start_date, end_date))
    return date_ranges

@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint om te controleren of de service actief is.
    """
    return jsonify({"status": "healthy", "message": "De service is actief en operationeel"}), 200

@app.route("/heart-rate-data", methods=["GET"])
def fetch_heart_rate_data():
    try:
        # Validatie van omgevingsvariabelen
        if not USERNAME or not PASSWORD:
            raise ValueError("Gebruikersnaam of wachtwoord is niet ingesteld als omgevingsvariabele.")

        logging.info("Verbinding maken met Garmin Connect...")
        client = Garmin(USERNAME, PASSWORD)
        client.login()
        logging.info("Succesvol ingelogd op Garmin Connect.")

        # Instellingen voor datumbereiken
        today = datetime.now()
        weeks_to_fetch = 2
        date_ranges = get_date_ranges(today, weeks_to_fetch)
        logging.info(f"Datumbereiken gegenereerd voor {weeks_to_fetch} weken.")

        weekly_heart_rate_data = {}

        for start_date, end_date in date_ranges:
            week_key = f"{start_date.strftime('%Y-%m-%d')} tot {end_date.strftime('%Y-%m-%d')}"
            logging.info(f"Gegevens ophalen voor week: {week_key}...")

            try:
                # Combineer dagelijkse gegevens binnen de week
                week_data = []
                for i in range(7):
                    cdate = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
                    try:
                        daily_data = client.get_heart_rates(cdate)
                        if daily_data and "heartRateValues" in daily_data:
                            heart_rate_values = [
                                value[1] for value in daily_data["heartRateValues"] if value[1] is not None
                            ]
                            if heart_rate_values:
                                logging.info(f"  {len(heart_rate_values)} geldige metingen gevonden voor {cdate}.")
                                # Voeg elke hartslagwaarde met een duur van 2 minuten toe
                                week_data.extend([{"heartRate": hr, "duration": 120} for hr in heart_rate_values])
                            else:
                                logging.info(f"  Geen geldige metingen gevonden voor {cdate}.")
                        else:
                            logging.info(f"  Geen gegevens beschikbaar voor {cdate}.")
                    except Exception as e:
                        logging.error(f"  Fout bij ophalen van gegevens voor {cdate}: {e}")

                # Controleer of er gegevens zijn voor de week
                if not week_data:
                    logging.info(f"Geen gegevens beschikbaar voor week {week_key}.")
                    continue

                # Groeperen en analyseren van gegevens
                grouped_data = group_heart_rate_data(week_data)
                logging.info(f"Gegevens gegroepeerd in intervallen van {HEART_RATE_RANGE_STEP} bpm.")

                total_time, percentages = calculate_percentages(grouped_data)
                logging.info(f"Totale tijd: {total_time // 60} minuten.")
                for range_key, percent in percentages.items():
                    logging.info(f"  {range_key}: {percent:.2f}% van de tijd.")

                # Opslaan in overzicht
                weekly_heart_rate_data[week_key] = {
                    "grouped_data": grouped_data,
                    "total_time_minutes": total_time // 60,
                    "percentages": percentages,
                }

            except Exception as e:
                logging.error(f"Fout bij het verwerken van gegevens voor week {week_key}: {e}")

        logging.info("Alle gegevens succesvol verwerkt.")
        return jsonify(weekly_heart_rate_data)

    except GarminConnectConnectionError as conn_err:
        logging.error(f"Verbindingsfout met Garmin Connect: {conn_err}")
        return jsonify({"error": "Verbindingsfout met Garmin Connect"}), 500
    except GarminConnectTooManyRequestsError as too_many_requests_err:
        logging.error(f"Te veel aanvragen: {too_many_requests_err}")
        return jsonify({"error": "Te veel aanvragen"}), 429
    except ValueError as ve:
        logging.error(f"Validatiefout: {ve}")
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logging.error(f"Onverwachte fout: {e}")
        return jsonify({"error": "Onverwachte fout"}), 500



if __name__ == "__main__":
    from waitress import serve
    # Gebruik poort 8080, zoals vereist door Cloud Run
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
