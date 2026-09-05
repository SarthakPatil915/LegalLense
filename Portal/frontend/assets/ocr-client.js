/* Thin fetch wrapper for the LegalLens OCR backend (FastAPI + PaddleOCR).
   Kept separate from app.js (the local mock-data/session layer) since this
   is the one module in the frontend that actually talks to a real server. */
(function (global) {
  "use strict";

  var DEFAULT_BASE_URL = "http://localhost:8000";
  var ALLOWED_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
  var ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];

  function getExtension(filename) {
    var idx = filename.lastIndexOf(".");
    return idx === -1 ? "" : filename.slice(idx).toLowerCase();
  }

  function validateFile(file) {
    if (!file) return "No file selected.";
    var ext = getExtension(file.name || "");
    var typeOk = !file.type || ALLOWED_TYPES.indexOf(file.type.toLowerCase()) !== -1;
    var extOk = ALLOWED_EXTENSIONS.indexOf(ext) !== -1;
    if (!typeOk && !extOk) {
      return "Unsupported file type. Please upload a JPG, JPEG, PNG, or WEBP image.";
    }
    return null;
  }

  function runOcr(file, baseUrl) {
    var url = (baseUrl || DEFAULT_BASE_URL) + "/api/ocr";
    var formData = new FormData();
    formData.append("file", file, file.name);

    return fetch(url, { method: "POST", body: formData, credentials: "include" })
      .then(function (response) {
        return response.json().then(function (data) {
          return { httpOk: response.ok, status: response.status, data: data };
        });
      })
      .catch(function (networkErr) {
        return {
          httpOk: false,
          status: 0,
          data: {
            success: false,
            image: file.name,
            error: {
              code: "network_error",
              message: "Could not reach the OCR backend at " + url + ". Is it running? (" + networkErr.message + ")",
            },
          },
        };
      });
  }

  function createScan(file, metadata, baseUrl) {
    var url = (baseUrl || DEFAULT_BASE_URL) + "/api/scans";
    var formData = new FormData();
    formData.append("file", file, file.name);
    formData.append("product_name", metadata.productName || file.name);
    formData.append("category", metadata.category || "General");
    formData.append("manufacturer", metadata.manufacturer || "Not specified");

    return fetch(url, { method: "POST", body: formData, credentials: "include" })
      .then(function (response) {
        return response.json().then(function (data) {
          return { httpOk: response.ok, status: response.status, data: data };
        });
      })
      .catch(function (networkErr) {
        return { httpOk: false, status: 0, data: { success: false, error: { code: "network_error", message: networkErr.message } } };
      });
  }

  function getScans(baseUrl) {
    return fetch((baseUrl || DEFAULT_BASE_URL) + "/api/scans", { credentials: "include", cache: "no-store" }).then(function (response) { return response.json(); });
  }

  function getScan(id, baseUrl) {
    return fetch((baseUrl || DEFAULT_BASE_URL) + "/api/scans/" + encodeURIComponent(id), { credentials: "include", cache: "no-store" }).then(function (response) {
      if (!response.ok) return null;
      return response.json();
    });
  }

  function evaluateCompliance(ocrResult, profile, baseUrl) {
    var url = (baseUrl || DEFAULT_BASE_URL) + "/api/compliance/evaluate";
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ ocr_result: ocrResult, validation_profile: profile || "e_commerce_product_listing" })
    }).then(function (response) {
      return response.json().then(function (data) {
        return { httpOk: response.ok, status: response.status, data: data };
      });
    }).catch(function (networkErr) {
      return { httpOk: false, status: 0, data: { detail: "Could not reach the compliance backend. " + networkErr.message } };
    });
  }

  function getCases(baseUrl) {
    return fetch((baseUrl || DEFAULT_BASE_URL) + "/api/cases", { credentials: "include" }).then(function (response) { return response.json(); });
  }

  global.LLOcr = {
    runOcr: runOcr,
    createScan: createScan,
    getScans: getScans,
    getScan: getScan,
    evaluateCompliance: evaluateCompliance,
    getCases: getCases,
    validateFile: validateFile,
    DEFAULT_BASE_URL: DEFAULT_BASE_URL,
  };
})(window);
