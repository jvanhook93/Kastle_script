from flask import Flask, request, send_file, jsonify
import pandas as pd
import numpy as np
from werkzeug.utils import secure_filename
import os
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.before_request
def log_req():
    print("REQ:", request.method, request.path)


@app.route("/", methods=["GET"])
def index():
    return "Backend running. Use /ping, POST /process, POST /process/attendance, POST /process/quick", 200


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "message": "Flask is alive!"})


@app.route("/routes", methods=["GET"])
def routes():
    return jsonify(sorted([str(r) for r in app.url_map.iter_rules()]))


# -----------------------------
# Helpers
# -----------------------------
def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _parse_dt_from_date_and_time(date_series: pd.Series, time_series: pd.Series) -> pd.Series:
    d = date_series.astype(str).str.strip()
    t = time_series.astype(str).str.replace(" CT", "", regex=False).str.strip()
    return pd.to_datetime(d + " " + t, errors="coerce")


def _parse_dt(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace(" CT", "", regex=False).str.strip()
    return pd.to_datetime(s, errors="coerce")


def _suite_from_reader(reader_text: str) -> str:
    if not isinstance(reader_text, str):
        return "Unknown"
    m = re.search(r"(Suite\s*\d+)", reader_text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else "Unknown"


def _safe_output_path(output_name: str, default_name: str) -> str:
    out = (output_name or "").strip() or default_name
    if not out.lower().endswith((".xlsx", ".xls")):
        out += ".xlsx"
    return os.path.join(UPLOAD_FOLDER, secure_filename(out))


def _load_df(file_storage) -> pd.DataFrame:
    name = (file_storage.filename or "").lower()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(file_storage)
        except Exception:
            file_storage.stream.seek(0)
            try:
                return pd.read_csv(file_storage, encoding="utf-8-sig")
            except Exception:
                file_storage.stream.seek(0)
                return pd.read_csv(file_storage, encoding_errors="ignore")
    return pd.read_excel(file_storage, engine="openpyxl")


def _looks_like_reader_activity(df: pd.DataFrame) -> bool:
    df = _norm_cols(df)
    reader_col = _find_col(df, ["Reader", "Reader Name", "Reader Description"])
    dt_col = _find_col(df, ["Date and Time", "Date & Time", "Datetime", "Date Time", "Time"])
    return reader_col is not None and dt_col is not None


def _excel_sheet_safe(name: str, fallback: str = "Unknown") -> str:
    s = (name or "").strip() or fallback
    s = re.sub(r"[:\\/?*\[\]]", "-", s)
    s = s.strip().strip("'")
    if not s:
        s = fallback
    return s[:31]


def _unique_sheet_name(base: str, used: set[str]) -> str:
    name = base[:31]
    if name not in used:
        used.add(name)
        return name

    i = 2
    while True:
        suffix = f" ({i})"
        trimmed = (base[: (31 - len(suffix))] + suffix) if len(base) > (31 - len(suffix)) else (base + suffix)
        trimmed = trimmed[:31]
        if trimmed not in used:
            used.add(trimmed)
            return trimmed
        i += 1


# -----------------------------
# Attendance Report (FIXED: groups by person)
# -----------------------------
def build_attendance_outputs(df_raw: pd.DataFrame, source_filename: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _norm_cols(df_raw)

    name_col = _find_col(df, ["Personnel Name", "Employee", "Name"])
    date_col = _find_col(df, ["Date", "Day", "Report Date"])
    entry_col = _find_col(df, ["Time Of First CardRead", "Time Of First Card Read", "Entry Time", "First In", "First Card Read"])
    exit_col = _find_col(df, ["Time Of Last Card Read", "Time Of Last CardRead", "Exit Time", "Last Out", "Last Card Read"])

    def fmt_hhmm(seconds):
        if seconds is None or pd.isna(seconds) or seconds <= 0:
            return "N/A"
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, _ = divmod(rem, 60)
        return f"{h:02d}:{m:02d}"

    # Header-based attendance file
    if name_col and date_col and entry_col and exit_col:
        work = df.copy()
        work["Employee"] = work[name_col].astype(str).str.strip().replace("", "Unknown")
        work["Date"] = work[date_col].astype(str).str.strip()

        work["EntryDT"] = _parse_dt_from_date_and_time(work["Date"], work[entry_col])
        work["ExitDT"] = _parse_dt_from_date_and_time(work["Date"], work[exit_col])

        work["DurationSeconds"] = (work["ExitDT"] - work["EntryDT"]).dt.total_seconds()
        work["DurationSeconds"] = pd.to_numeric(work["DurationSeconds"], errors="coerce")

        grp = work.groupby("Employee", dropna=False)
        summary = grp.agg(
            Days_in_Office=("Date", lambda s: s.nunique()),
            TotalSeconds=("DurationSeconds", "sum"),
        ).reset_index()

        summary_df = pd.DataFrame({
            "Name": summary["Employee"],
            "Days in Office": summary["Days_in_Office"],
            "Time in Office (HH:MM)": summary["TotalSeconds"].apply(fmt_hhmm),
            "Average Time per Day (HH:MM)": summary.apply(
                lambda r: fmt_hhmm(r["TotalSeconds"] / r["Days_in_Office"]) if r["Days_in_Office"] else "N/A",
                axis=1
            ),
            "Source File": source_filename
        })

        combined_df = work.copy()
        combined_df.insert(0, "Source File", source_filename)
        combined_df["Duration (minutes)"] = (combined_df["DurationSeconds"] / 60.0).round(2)

        # Keep Employee near front
        cols = list(combined_df.columns)
        if "Employee" in cols:
            cols.insert(1, cols.pop(cols.index("Employee")))
            combined_df = combined_df[cols]

        return summary_df, combined_df

    # Fallback: legacy positional format (>=7 columns)
    if df_raw is None or df_raw.empty or df_raw.shape[1] < 7:
        raise ValueError("Attendance file format not recognized (missing headers and < 7 columns).")

    legacy = df_raw.copy()
    legacy["Employee"] = legacy.iloc[:, 1].astype(str).str.strip().replace("", "Unknown")
    legacy["EntryDT"] = _parse_dt(legacy.iloc[:, 3])
    legacy["ExitDT"] = _parse_dt(legacy.iloc[:, 6])
    legacy["DurationSeconds"] = (legacy["ExitDT"] - legacy["EntryDT"]).dt.total_seconds()
    legacy["DurationSeconds"] = pd.to_numeric(legacy["DurationSeconds"], errors="coerce")

    grp = legacy.groupby("Employee", dropna=False)
    summary = grp.agg(
        Days_in_Office=("Employee", "size"),
        TotalSeconds=("DurationSeconds", "sum"),
    ).reset_index()

    summary_df = pd.DataFrame({
        "Name": summary["Employee"],
        "Days in Office": summary["Days_in_Office"],
        "Time in Office (HH:MM)": summary["TotalSeconds"].apply(fmt_hhmm),
        "Average Time per Day (HH:MM)": summary.apply(
            lambda r: fmt_hhmm(r["TotalSeconds"] / r["Days_in_Office"]) if r["Days_in_Office"] else "N/A",
            axis=1
        ),
        "Source File": source_filename
    })

    combined_df = legacy.copy()
    combined_df.insert(0, "Source File", source_filename)
    combined_df["Duration (minutes)"] = (combined_df["DurationSeconds"] / 60.0).round(2)
    return summary_df, combined_df


# -----------------------------
# Quick Custom Report (Reader Activity)
# -----------------------------
def build_suite_sessions(reader_df: pd.DataFrame):
    df = _norm_cols(reader_df)

    reader_col = _find_col(df, ["Reader", "Reader Name", "Reader Description"])
    dt_col = _find_col(df, ["Date and Time", "Date & Time", "Datetime", "Date Time", "Time"])

    if not reader_col or not dt_col:
        raise ValueError("Missing required columns for Reader Activity report (need Reader + Date/Time).")

    if "Personnel Name" not in df.columns:
        df["Personnel Name"] = ""
    if "Card Number" not in df.columns:
        df["Card Number"] = ""

    df["dt"] = _parse_dt(df[dt_col])
    df = df.dropna(subset=["dt"]).copy()

    r = df[reader_col].astype(str).str.lower()
    df["direction"] = np.select(
        [r.str.contains("entry"), r.str.contains("exit")],
        ["ENTRY", "EXIT"],
        default="OTHER"
    )

    df = df[df["direction"].isin(["ENTRY", "EXIT"])].copy()
    if df.empty:
        raise ValueError("No ENTRY/EXIT rows found (Reader column did not contain 'entry' or 'exit').")

    df["Suite"] = df[reader_col].apply(_suite_from_reader)
    df["Personnel Name"] = df["Personnel Name"].astype(str).str.strip().replace("", "Unknown")
    df["Card Number"] = df["Card Number"].astype(str).str.strip()

    df = df.sort_values(["Personnel Name", "Card Number", "Suite", "dt"]).reset_index(drop=True)

    sessions = []
    open_state = {}
    last_dir = {}

    def key_for(row):
        return (
            str(row.get("Personnel Name", "")).strip() or "Unknown",
            str(row.get("Card Number", "")).strip(),
            str(row.get("Suite", "Unknown")).strip()
        )

    for _, row in df.iterrows():
        k = key_for(row)
        direction = row["direction"]
        when = row["dt"]
        reader = row.get(reader_col, "")
        prev = last_dir.get(k)

        if direction == "ENTRY":
            if k in open_state:
                sessions.append({
                    "Personnel Name": k[0],
                    "Card Number": k[1],
                    "Suite": k[2],
                    "Entry Reader": open_state[k]["entry_reader"],
                    "Entry Time": open_state[k]["entry_time"],
                    "Exit Reader": "",
                    "Exit Time": "",
                    "Duration (minutes)": "",
                    "Issue": "DOUBLE ENTRY (missing EXIT before this ENTRY)"
                })
            open_state[k] = {"entry_time": when, "entry_reader": reader}

        elif direction == "EXIT":
            if k not in open_state:
                issue = "EXIT WITHOUT ENTRY"
                if prev == "EXIT":
                    issue = "DOUBLE EXIT (expected ENTRY between EXITs)"
                sessions.append({
                    "Personnel Name": k[0],
                    "Card Number": k[1],
                    "Suite": k[2],
                    "Entry Reader": "",
                    "Entry Time": "",
                    "Exit Reader": reader,
                    "Exit Time": when,
                    "Duration (minutes)": "",
                    "Issue": issue
                })
            else:
                entry_time = open_state[k]["entry_time"]
                duration_min = round((when - entry_time).total_seconds() / 60.0, 2)
                issue = "NEGATIVE DURATION (timestamps out of order?)" if duration_min < 0 else ""

                sessions.append({
                    "Personnel Name": k[0],
                    "Card Number": k[1],
                    "Suite": k[2],
                    "Entry Reader": open_state[k]["entry_reader"],
                    "Entry Time": entry_time,
                    "Exit Reader": reader,
                    "Exit Time": when,
                    "Duration (minutes)": duration_min,
                    "Issue": issue
                })
                open_state.pop(k, None)

        last_dir[k] = direction

    for k, state in open_state.items():
        sessions.append({
            "Personnel Name": k[0],
            "Card Number": k[1],
            "Suite": k[2],
            "Entry Reader": state["entry_reader"],
            "Entry Time": state["entry_time"],
            "Exit Reader": "",
            "Exit Time": "",
            "Duration (minutes)": "",
            "Issue": "MISSING EXIT"
        })

    sessions_df = pd.DataFrame(sessions)
    if sessions_df.empty:
        raise ValueError("No sessions produced after pairing. (Unexpected)")

    discrepancies_df = sessions_df[sessions_df["Issue"].astype(str).str.strip() != ""].copy()

    tmp = sessions_df.copy()
    tmp["Entry Time"] = pd.to_datetime(tmp["Entry Time"], errors="coerce")
    tmp["Exit Time"] = pd.to_datetime(tmp["Exit Time"], errors="coerce")
    tmp["Duration (minutes)"] = pd.to_numeric(tmp["Duration (minutes)"], errors="coerce")

    completed = tmp.dropna(subset=["Entry Time", "Exit Time", "Duration (minutes)"]).copy()
    completed["Date"] = completed["Entry Time"].dt.date

    summary_df = (
        completed
        .groupby(["Personnel Name", "Card Number", "Suite", "Date"], dropna=False)["Duration (minutes)"]
        .sum()
        .reset_index()
        .sort_values(["Personnel Name", "Date", "Suite"])
    )

    return sessions_df, discrepancies_df, summary_df


# -----------------------------
# Processors
# -----------------------------
def _process_attendance(files, output_name):
    output_path = _safe_output_path(output_name, "Attendance_Output.xlsx")

    summary_frames = []
    combined_frames = []
    skipped_files = []
    file_errors = []

    for f in files:
        try:
            df = _load_df(f)
        except Exception as e:
            skipped_files.append(f.filename)
            file_errors.append({"file": f.filename, "stage": "read", "error": str(e)})
            continue

        if df is None or df.empty:
            skipped_files.append(f.filename)
            file_errors.append({"file": f.filename, "stage": "validate", "error": "Empty file"})
            continue

        try:
            s_df, c_df = build_attendance_outputs(df, f.filename)
            if not s_df.empty:
                summary_frames.append(s_df)
            if c_df is not None and not c_df.empty:
                combined_frames.append(c_df)
        except Exception as e:
            skipped_files.append(f.filename)
            file_errors.append({"file": f.filename, "stage": "attendance", "error": str(e)})
            continue

    if not summary_frames:
        return None, {
            "error": "No valid data processed",
            "skipped_files": skipped_files,
            "file_errors": file_errors
        }

    summary_df = pd.concat(summary_frames, ignore_index=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        if combined_frames:
            pd.concat(combined_frames, ignore_index=True).to_excel(writer, sheet_name="Combined", index=False)

    return output_path, None


def _process_quick(files, output_name):
    output_path = _safe_output_path(output_name, "Quick_Custom_Output.xlsx")

    all_sessions = []
    all_discrepancies = []
    all_summaries = []
    combined_frames = []
    skipped_files = []
    file_errors = []

    # ✅ Per-person bucket across all uploaded files
    per_person_sessions: dict[str, list[pd.DataFrame]] = {}
    per_person_issues: dict[str, list[pd.DataFrame]] = {}
    per_person_summary: dict[str, list[pd.DataFrame]] = {}

    for f in files:
        try:
            df = _load_df(f)
        except Exception as e:
            skipped_files.append(f.filename)
            file_errors.append({"file": f.filename, "stage": "read", "error": str(e)})
            continue

        if df is None or df.empty:
            skipped_files.append(f.filename)
            file_errors.append({"file": f.filename, "stage": "validate", "error": "Empty file"})
            continue

        try:
            sessions_df, discrepancies_df, summary_df = build_suite_sessions(df)

            # Overall sheets
            sessions_df.insert(0, "Source File", f.filename)
            all_sessions.append(sessions_df)

            if not discrepancies_df.empty:
                discrepancies_df.insert(0, "Source File", f.filename)
                all_discrepancies.append(discrepancies_df)

            if not summary_df.empty:
                summary_df.insert(0, "Source File", f.filename)
                all_summaries.append(summary_df)

            df2 = _norm_cols(df).copy()
            df2.insert(0, "Source File", f.filename)
            combined_frames.append(df2)

            # ✅ Split into per-person tabs
            sessions_df["Personnel Name"] = sessions_df["Personnel Name"].astype(str).str.strip().replace("", "Unknown")

            for person, chunk in sessions_df.groupby("Personnel Name", dropna=False):
                per_person_sessions.setdefault(person, []).append(chunk)

            if not discrepancies_df.empty:
                discrepancies_df["Personnel Name"] = discrepancies_df["Personnel Name"].astype(str).str.strip().replace("", "Unknown")
                for person, chunk in discrepancies_df.groupby("Personnel Name", dropna=False):
                    per_person_issues.setdefault(person, []).append(chunk)

            if not summary_df.empty:
                summary_df["Personnel Name"] = summary_df["Personnel Name"].astype(str).str.strip().replace("", "Unknown")
                for person, chunk in summary_df.groupby("Personnel Name", dropna=False):
                    per_person_summary.setdefault(person, []).append(chunk)

        except Exception as e:
            skipped_files.append(f.filename)
            file_errors.append({"file": f.filename, "stage": "quick", "error": str(e)})
            continue

    if not all_sessions:
        return None, {
            "error": "No valid data processed",
            "skipped_files": skipped_files,
            "file_errors": file_errors
        }

    used = set()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Overall
        pd.concat(all_sessions, ignore_index=True).to_excel(writer, sheet_name="Suite Sessions", index=False)
        if all_discrepancies:
            pd.concat(all_discrepancies, ignore_index=True).to_excel(writer, sheet_name="Suite Discrepancies", index=False)
        if all_summaries:
            pd.concat(all_summaries, ignore_index=True).to_excel(writer, sheet_name="Suite Summary", index=False)
        if combined_frames:
            pd.concat(combined_frames, ignore_index=True).to_excel(writer, sheet_name="Combined", index=False)

        # Per-person tabs
        for person in sorted(per_person_sessions.keys(), key=lambda x: str(x).lower()):
            safe_person = _excel_sheet_safe(str(person), fallback="Unknown")

            sess_name = _unique_sheet_name(f"{safe_person} - Sessions", used)
            pd.concat(per_person_sessions[person], ignore_index=True).to_excel(writer, sheet_name=sess_name, index=False)

            if person in per_person_issues and per_person_issues[person]:
                iss_name = _unique_sheet_name(f"{safe_person} - Issues", used)
                pd.concat(per_person_issues[person], ignore_index=True).to_excel(writer, sheet_name=iss_name, index=False)

            if person in per_person_summary and per_person_summary[person]:
                sum_name = _unique_sheet_name(f"{safe_person} - Summary", used)
                pd.concat(per_person_summary[person], ignore_index=True).to_excel(writer, sheet_name=sum_name, index=False)

    return output_path, None


# -----------------------------
# Endpoints
# -----------------------------
@app.route("/process/attendance", methods=["POST"])
@app.route("/process/attendance/", methods=["POST"])
def process_attendance():
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400
    files = request.files.getlist("files")
    output_path, err = _process_attendance(files, request.form.get("output_name"))
    if err:
        return jsonify(err), 400
    return send_file(output_path, as_attachment=True)


@app.route("/process/quick", methods=["POST"])
@app.route("/process/quick/", methods=["POST"])
def process_quick():
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400
    files = request.files.getlist("files")
    output_path, err = _process_quick(files, request.form.get("output_name"))
    if err:
        return jsonify(err), 400
    return send_file(output_path, as_attachment=True)


@app.route("/process", methods=["POST"])
@app.route("/process/", methods=["POST"])
def process_compat():
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    report_type = (request.form.get("report_type") or "").strip().lower()
    files = request.files.getlist("files")

    if report_type == "attendance":
        output_path, err = _process_attendance(files, request.form.get("output_name"))
    elif report_type == "quick":
        output_path, err = _process_quick(files, request.form.get("output_name"))
    else:
        try:
            first_df = _load_df(files[0])
        except Exception as e:
            return jsonify({"error": "Could not read uploaded file", "details": str(e)}), 400

        if _looks_like_reader_activity(first_df):
            output_path, err = _process_quick(files, request.form.get("output_name"))
        else:
            output_path, err = _process_attendance(files, request.form.get("output_name"))

    if err:
        return jsonify(err), 400
    return send_file(output_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
