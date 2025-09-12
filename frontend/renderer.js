window.addEventListener("DOMContentLoaded", () => {
  const dropArea = document.getElementById("drop-area");
  const outputNameInput = document.getElementById("output-name");
  const submitBtn = document.getElementById("submit-btn");

  let droppedFiles = [];

  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  dropArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropArea.classList.add("hover");
  });

  dropArea.addEventListener("dragleave", (e) => {
    dropArea.classList.remove("hover");
  });

  dropArea.addEventListener("drop", (e) => {
    e.preventDefault();
    dropArea.classList.remove("hover");
    droppedFiles = Array.from(e.dataTransfer.files);
    dropArea.innerText = `${droppedFiles.length} file(s) ready to process`;
  });

  submitBtn.addEventListener("click", async () => {
    if (droppedFiles.length === 0) return alert("Please drag at least one file!");
    const outputName = outputNameInput.value || "Merged_Kastle_Reports_WithSummary.xlsx";
    const formData = new FormData();

    try {
      for (const file of droppedFiles) {
        const buffer = await file.arrayBuffer();
        const blob = new Blob([buffer], { type: file.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
        formData.append("files", new File([blob], file.name));
      }
      formData.append("output_name", outputName);

      const res = await fetch("http://127.0.0.1:5000/process", { method: "POST", body: formData });

      if (!res.ok) {
        const resClone = res.clone();
        let errMsg;
        try {
          const data = await res.json();
          errMsg = data.error || "Unknown error";
          if (data.skipped_files && data.skipped_files.length > 0) {
            errMsg += `\nSkipped files: ${data.skipped_files.join(", ")}`;
          }
        } catch {
          errMsg = await resClone.text(); // read from clone
        }
        throw new Error(errMsg);
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = outputName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      dropArea.innerText = "Drop files here";
      droppedFiles = [];
      outputNameInput.value = "";

    } catch (err) {
      console.error(err);
      alert(`Error processing files:\n${err.message}`);
    }
  });


  let pingAttempts = 0;
  const maxPingAttempts = 5;

  const pingBackend = async () => {
    if (pingAttempts >= maxPingAttempts) return;
    pingAttempts++;

    try {
      const res = await fetch("http://127.0.0.1:5000/ping");
      if (!res.ok) throw new Error("Ping failed");
      const data = await res.json();
      console.log("Backend ping response:", data);
    } catch (err) {
      console.warn(`Ping attempt ${pingAttempts} failed.`);
      setTimeout(pingBackend, 2000);
    }
  };

  pingBackend();
});
