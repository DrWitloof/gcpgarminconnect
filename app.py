from flask import Flask, jsonify, request
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

        # Queryparameters ophalen
        to_date = request.args.get("to_date")
        from_date = request.args.get("from_date")

        # Standaardwaarde voor to_date: gisteren
        if not to_date:
            to_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Standaardwaarde voor from_date: 7 dagen vóór to_date
        if not from_date:
            from_date = (datetime.strptime(to_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

        try:
            start_date = datetime.strptime(from_date, "%Y-%m-%d")
            end_date = datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Ongeldig datumformaat. Gebruik 'YYYY-MM-DD'.")

        if start_date > end_date:
            raise ValueError("'from_date' mag niet later zijn dan 'to_date'.")

        logging.info(f"Gegevens ophalen van {from_date} tot {to_date}.")

        logging.info("Verbinding maken met Garmin Connect...")
        client = Garmin(USERNAME, PASSWORD)
        client.login()
        logging.info("Succesvol ingelogd op Garmin Connect.")

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
                    if heart_rate_values:
                        logging.info(f"  {len(heart_rate_values)} geldige metingen gevonden voor {cdate}.")
                        combined_data.extend([{"heartRate": hr, "duration": 120} for hr in heart_rate_values])
                    else:
                        logging.info(f"  Geen geldige metingen gevonden voor {cdate}.")
                else:
                    logging.info(f"  Geen gegevens beschikbaar voor {cdate}.")
            except Exception as e:
                logging.error(f"  Fout bij ophalen van gegevens voor {cdate}: {e}")
            current_date += timedelta(days=1)

        if not combined_data:
            logging.info("Geen gegevens beschikbaar voor de opgegeven periode.")
            return jsonify({"message": "Geen gegevens beschikbaar voor de opgegeven periode."}), 404

        # Groeperen en analyseren van gegevens
        grouped_data = group_heart_rate_data(combined_data)
        logging.info(f"Gegevens gegroepeerd in intervallen van {HEART_RATE_RANGE_STEP} bpm.")

        total_time, percentages = calculate_percentages(grouped_data)
        logging.info(f"Totale tijd: {total_time // 60} minuten.")
        for range_key, percent in percentages.items():
            logging.info(f"  {range_key}: {percent:.2f}% van de tijd.")

        result = {
            "from_date": from_date,
            "to_date": to_date,
            "grouped_data": grouped_data,
            "total_time_minutes": total_time // 60,
            "percentages": {k: percentages[k] for k in sorted(percentages)},
        }

        return jsonify(result)

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
