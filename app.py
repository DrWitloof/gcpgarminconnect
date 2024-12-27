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
    grouped_data = defaultdict(int)
    for entry in heart_rate_data:
        heart_rate = entry.get("heartRate", 0)
        time_in_seconds = entry.get("duration", 0)
        range_key = f"{(heart_rate // HEART_RATE_RANGE_STEP) * HEART_RATE_RANGE_STEP}-" \
                    f"{(heart_rate // HEART_RATE_RANGE_STEP) * HEART_RATE_RANGE_STEP + (HEART_RATE_RANGE_STEP - 1)}"
        grouped_data[range_key] += time_in_seconds
    return grouped_data

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
        if not USERNAME or not PASSWORD:
            raise ValueError("Gebruikersnaam of wachtwoord is niet ingesteld als omgevingsvariabele.")

        client = Garmin(USERNAME, PASSWORD)
        client.login()
        logging.info("Succesvol ingelogd!")

        today = datetime.now()
        weeks_to_fetch = 20
        date_ranges = get_date_ranges(today, weeks_to_fetch)

        weekly_heart_rate_data = {}

        for start_date, end_date in date_ranges:
            week_key = f"{start_date.strftime('%Y-%m-%d')} tot {end_date.strftime('%Y-%m-%d')}"
            try:
                heart_rate_data = client.get_heart_rates_between_dates(
                    start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
                )
                if not heart_rate_data:
                    logging.info(f"Geen gegevens beschikbaar voor week {week_key}.")
                    continue

                grouped_data = group_heart_rate_data(heart_rate_data)
                total_time, percentages = calculate_percentages(grouped_data)
                weekly_heart_rate_data[week_key] = {
                    "grouped_data": grouped_data,
                    "total_time_minutes": total_time // 60,
                    "percentages": percentages,
                }
            except Exception as e:
                logging.error(f"Fout bij ophalen van week {week_key}: {e}")

        return jsonify(weekly_heart_rate_data)

    except GarminConnectConnectionError as conn_err:
        logging.error(f"Verbindingsfout: {conn_err}")
        return jsonify({"error": "Verbindingsfout"}), 500
    except GarminConnectTooManyRequestsError as too_many_requests_err:
        logging.error(f"Te veel aanvragen: {too_many_requests_err}")
        return jsonify({"error": "Te veel aanvragen"}), 429
    except ValueError as ve:
        logging.error(str(ve))
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logging.error(f"Onverwachte fout: {e}")
        return jsonify({"error": "Onverwachte fout"}), 500

if __name__ == "__main__":
    from waitress import serve
    # Gebruik poort 8080, zoals vereist door Cloud Run
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
