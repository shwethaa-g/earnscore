import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import "./i18n";
import { AuthProvider, RequireRole } from "./lib/auth";
import { AppShell } from "./components/shell";
import { Landing, Login, NotFound, Register } from "./pages/Public";
import * as W from "./pages/worker";
import * as O from "./pages/officer";
import * as A from "./pages/admin";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/worker" element={<RequireRole role="worker"><AppShell role="worker" /></RequireRole>}>
              <Route index element={<W.Passport />} />
              <Route path="sources" element={<W.Sources />} />
              <Route path="consents" element={<W.Consents />} />
              <Route path="improve" element={<W.Improve />} />
              <Route path="share" element={<W.Share />} />
              <Route path="disputes" element={<W.Disputes />} />
              <Route path="profile" element={<W.Profile />} />
            </Route>
            <Route path="/officer" element={<RequireRole role="officer"><AppShell role="officer" /></RequireRole>}>
              <Route index element={<O.Queue />} />
              <Route path="applications/:id" element={<O.Report />} />
              <Route path="portfolio" element={<O.Portfolio />} />
              <Route path="disputes" element={<O.DisputesInbox />} />
            </Route>
            <Route path="/admin" element={<RequireRole role="admin"><AppShell role="admin" /></RequireRole>}>
              <Route index element={<A.Models />} />
              <Route path="validation" element={<A.Validation />} />
              <Route path="fairness" element={<A.Fairness />} />
              <Route path="drift" element={<A.Drift />} />
              <Route path="overrides" element={<A.Overrides />} />
              <Route path="audit" element={<A.Audit />} />
              <Route path="users" element={<A.Users />} />
              <Route path="disputes" element={<O.DisputesInbox />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
