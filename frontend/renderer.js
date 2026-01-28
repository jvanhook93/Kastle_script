window.addEventListener("DOMContentLoaded", () => {
  // Screens
  const screenHome = document.getElementById("screen-home");
  const screenRunner = document.getElementById("screen-runner");

  // Home buttons
  const btnAttendance = document.getElementById("btn-attendance");
  const btnQuick = document.getElementById("btn-quick");

  // Runner UI
  const btnBack = document.getElementById("btn-back");
  const runnerTitle = document.getElementById("runner-title");
  const runnerHint = document.getElementById("runner-hint");

  const dropArea = document.getElementById("drop-area");
  const fileInput = document.getElementById("file-input");
  const outputNameInput = document.getElementById("output-name");
  const submitBtn = document.getElementById("submit-btn");

  // Status + splash
  const statusPill = document.getElementById("status-pill");
  const splash = document.getElementById("splash");
  const splashMsg = document.getElementById("splash-msg");

  let droppedFiles = [];
  let activeReport = null; // "attendance" | "quick"

  function setStatus(state, text) {
    if (!statusPill) return;

    statusPill.classList.remove("spin", "ok", "bad");

    if (state === "checking" || state === "starting") statusPill.classList.add("spin");
    if (state === "ready") statusPill.classList.add("ok");
    if (state === "error") statusPill.classList.add("bad");

    statusPill.textContent = text || "Backend: checking…";
  }

  function setSplash(show, msg) {
    if (!splash) return;
    splash.classList.toggle("show", !!show);
    if (splashMsg && msg) splashMsg.textContent = msg;
  }

  function showHome() {
    activeReport = null;
    droppedFiles = [];
    dropArea.innerText = "Drop Excel/CSV files here";
    outputNameInput.value = "";
    fileInput.value = "";
    runnerTitle.innerText = "Report";
    runnerHint.innerText = "";
    screenRunner.classList.add("hidden");
    screenHome.classList.remove("hidden");
  }

  function showRunner(reportType) {
    activeReport = reportType;

    screenHome.classList.add("hidden");
    screenRunner.classList.remove("hidden");

    if (reportType === "attendance") {
      runnerTitle.innerText = "Attendance Report";
      runnerHint.innerText = "Drop Attendance exports (Excel/CSV). Output includes Summary + Combined.";
      dropArea.innerText = "Drop Attendance exports here";
      outputNameInput.placeholder = "Output filename (optional) - Attendance_Output.xlsx";
    } else if (reportType === "quick") {
      runnerTitle.innerText = "Suite Sessions (Custom)";
      runnerHint.innerText = "Drop Reader Activity exports. Output includes Suite Sessions + Discrepancies + Summary.";
      dropArea.innerText = "Drop Reader Activity exports here";
      outputNameInput.placeholder = "Output filename (optional) - Quick_Custom_Output.xlsx";
    }
  }

  function endpointForReport(reportType) {
    if (reportType === "attendance") return "http://127.0.0.1:5000/process/attendance";
    if (reportType === "quick") return "http://127.0.0.1:5000/process/quick";
    return null;
  }

  function setFiles(filesArray) {
    droppedFiles = filesArray || [];
    dropArea.innerText =
      droppedFiles.length === 0
        ? "Drop Excel/CSV files here"
        : `${droppedFiles.length} file(s) ready to process`;
  }

  // Home actions
  btnAttendance?.addEventListener("click", () => showRunner("attendance"));
  btnQuick?.addEventListener("click", () => showRunner("quick"));
  btnBack?.addEventListener("click", () => showHome());

  // Drag/drop behavior
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  dropArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropArea.classList.add("hover");
  });

  dropArea.addEventListener("dragleave", () => {
    dropArea.classList.remove("hover");
  });

  dropArea.addEventListener("drop", (e) => {
    e.preventDefault();
    dropArea.classList.remove("hover");
    const files = Array.from(e.dataTransfer.files || []);
    setFiles(files);
  });

  // File picker
  fileInput?.addEventListener("change", (e) => {
    const files = Array.from(e.target.files || []);
    setFiles(files);
  });

  // Submit
  submitBtn.addEventListener("click", async () => {
    try {
      if (!activeReport) return alert("Pick a report type first.");
      if (droppedFiles.length === 0) return alert("Please add at least one file.");

      const url = endpointForReport(activeReport);
      if (!url) throw new Error("Invalid report type.");

      const outputName =
        (outputNameInput.value || "").trim() ||
        (activeReport === "attendance" ? "Attendance_Output.xlsx" : "Quick_Custom_Output.xlsx");

      const formData = new FormData();
      for (const file of droppedFiles) formData.append("files", file, file.name);
      formData.append("output_name", outputName);

      const res = await fetch(url, { method: "POST", body: formData });

      if (!res.ok) {
        let errMsg = `Server error (${res.status})`;
        const ct = (res.headers.get("content-type") || "").toLowerCase();
        if (ct.includes("application/json")) {
          const data = await res.json();
          errMsg = data.error || errMsg;
          if (data.skipped_files?.length) errMsg += `\nSkipped: ${data.skipped_files.join(", ")}`;
          if (data.file_errors?.length) errMsg += `\n\nDetails:\n${JSON.stringify(data.file_errors[0], null, 2)}`;
        } else {
          errMsg = await res.text();
        }
        throw new Error(errMsg);
      }

      const blob = await res.blob();
      const dlUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = dlUrl;
      a.download = outputName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(dlUrl);

      setFiles([]);
      outputNameInput.value = "";
      fileInput.value = "";

    } catch (err) {
      console.error(err);
      alert(`Error processing files:\n${err.message || err}`);
    }
  });

  // --- Backend status wiring ---
  // If preload exposes window.inet, use it. Otherwise fallback to ping loop.
  setStatus("checking", "Backend: checking…");
  setSplash(true, "Launching backend…");

  if (window.inet && window.inet.requestStatus) {
    window.inet.requestStatus();
  }

  if (window.inet && typeof window.inet.onBackendStatus === "function") {
    window.inet.onBackendStatus(({ status, detail }) => {
      if (status === "starting" || status === "checking") {
        setStatus("checking", `Backend: checking…`);
        setSplash(true, detail || "Starting backend…");
      } else if (status === "ready") {
        setStatus("ready", "Backend: online");
        setSplash(false);
      } else if (status === "error") {
        setStatus("error", "Backend: error");
        setSplash(true, detail || "Backend failed to start");
      }
    });
  } else {
    // Fallback ping loop (dev safe)
    (async function pingLoop() {
      for (let i = 0; i < 60; i++) {
        try {
          const res = await fetch("http://127.0.0.1:5000/ping");
          if (res.ok) {
            setStatus("ready", "Backend: online");
            setSplash(false);
            return;
          }
        } catch {}
        await new Promise((r) => setTimeout(r, 250));
      }
      setStatus("error", "Backend: error");
      setSplash(true, "Backend did not respond on /ping");
    })();
  }

  // Default view
  showHome();
});
