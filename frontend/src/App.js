import React, { useState } from "react";
import axios from "axios";

function App() {
  const [file, setFile] = useState(null);
  const [outputName, setOutputName] = useState("");
  const [message, setMessage] = useState("");

  const handleFileChange = (e) => setFile(e.target.files[0]);
  const handleOutputChange = (e) => setOutputName(e.target.value);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file || !outputName) {
      setMessage("Please select a file and enter output name");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("output_name", outputName);

    try {
      const response = await axios.post("http://127.0.0.1:5000/upload", formData, {
        responseType: "blob",
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${outputName}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setMessage("File processed successfully!");
    } catch (err) {
      setMessage("Error processing file");
    }
  };

  return (
    <div style={{ padding: "2rem" }}>
      <h2>Kastle Excel Processor</h2>
      <form onSubmit={handleSubmit}>
        <div>
          <input type="file" onChange={handleFileChange} accept=".xlsx" />
        </div>
        <div style={{ marginTop: "1rem" }}>
          <input type="text" placeholder="Output file name" value={outputName} onChange={handleOutputChange} />
        </div>
        <button type="submit" style={{ marginTop: "1rem" }}>Run</button>
      </form>
      <p>{message}</p>
    </div>
  );
}

export default App;
