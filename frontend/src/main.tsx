import React from "react";
import ReactDOM from "react-dom/client";
import { NewApp } from "./NewApp";
import "./new-styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <NewApp />
  </React.StrictMode>,
);
