from flask import Flask, request, send_file, jsonify
import pandas as pd
from werkzeug.utils import secure_filename
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "message": "Flask is alive!"})

@app.route("/process", methods=["POST"], strict_slashes=False)
def process_files():
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    output_name = request.form.get("output_name", "Merged_Kastle_Reports_WithSummary.xlsx")
    if not output_name.lower().endswith((".xlsx", ".xls")):
        output_name += ".xlsx"
    output_path = os.path.join(UPLOAD_FOLDER, secure_filename(output_name))

    summary_data = []
    skipped_files = []

    for f in files:
        filename = f.filename.lower()
        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(f, header=0)
            else:
                df = pd.read_excel(f, header=0)
        except Exception as e:
            print(f"Skipped {f.filename}, cannot read file: {e}")
            skipped_files.append(f.filename)
            continue

        if df.empty or df.shape[1] < 7:
            print(f"Skipped {f.filename}, not enough data")
            skipped_files.append(f.filename)
            continue

        try:
            employee_name = df.iloc[0, 1] if pd.notna(df.iloc[0, 1]) else "Unknown"

            days_in_office = len(df)

            entry_times = pd.to_datetime(
                df.iloc[:, 3].astype(str).str.replace(" CT", "", regex=False).str.strip(),
                errors="coerce"
            )
            exit_times = pd.to_datetime(
                df.iloc[:, 6].astype(str).str.replace(" CT", "", regex=False).str.strip(),
                errors="coerce"
            )

            total_seconds = 0
            for entry, exit_ in zip(entry_times, exit_times):
                if pd.notna(entry) and pd.notna(exit_):
                    delta = exit_ - entry
                    total_seconds += int(delta.total_seconds())

            if total_seconds == 0:
                total_time_str = "N/A"
                avg_time_str = "N/A"
            else:
                total_hours, remainder = divmod(total_seconds, 3600)
                total_minutes, _ = divmod(remainder, 60)
                total_time_str = f"{total_hours:02d}:{total_minutes:02d}"

                avg_seconds = total_seconds / days_in_office
                avg_hours, remainder = divmod(int(avg_seconds), 3600)
                avg_minutes, _ = divmod(remainder, 60)
                avg_time_str = f"{avg_hours:02d}:{avg_minutes:02d}"

            summary_data.append({
                "Name": employee_name,
                "Days in Office": days_in_office,
                "Time in Office (HH:MM)": total_time_str,
                "Average Time per Day (HH:MM)": avg_time_str
            })

        except Exception as e:
            print(f"Skipped {f.filename}, error processing data: {e}")
            skipped_files.append(f.filename)
            continue

    if not summary_data:
        return jsonify({
            "error": "No valid data processed",
            "skipped_files": skipped_files
        }), 400

    summary_df = pd.DataFrame(summary_data)
    summary_df.to_excel(output_path, index=False, engine="openpyxl")
    print(f"Saved summary to {output_path}")

    return send_file(output_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
