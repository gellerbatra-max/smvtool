import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { StyleListPage } from "./pages/StyleListPage";
import { LibraryPage } from "./pages/LibraryPage";
import { StyleEditorPage } from "./pages/StyleEditorPage";
import { BulletinPage } from "./pages/BulletinPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { UsersPage } from "./pages/UsersPage";
import { AllowancePolicyPage } from "./pages/AllowancePolicyPage";
import { RequireRole } from "./components/ProtectedRoute";
import { useTheme } from "./theme/useTheme";
import "./app.css";

function AppShell() {
  const { auth, forbiddenMessage, clearForbidden } = useAuth();
  const [theme, toggleTheme] = useTheme();
  return (
    <div className="app-shell">
      {auth && <TopBar theme={theme} onToggleTheme={toggleTheme} />}
      {forbiddenMessage && (
        <div className="toast toast-forbidden" role="alert">
          {forbiddenMessage}
          <button className="btn btn-ghost" onClick={clearForbidden}>
            ×
          </button>
        </div>
      )}
      <div className="app-body">
        {auth && <Sidebar />}
        <main className="app-main">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/styles"
            element={
              <ProtectedRoute>
                <StyleListPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/library"
            element={
              <ProtectedRoute>
                <LibraryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/styles/new"
            element={
              <ProtectedRoute>
                <StyleEditorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/styles/:id/edit"
            element={
              <ProtectedRoute>
                <StyleEditorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/styles/:id/bulletin"
            element={
              <ProtectedRoute>
                <BulletinPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/styles/:id/analytics"
            element={
              <ProtectedRoute>
                <AnalyticsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute>
                <RequireRole roles={["administrator"]}>
                  <UsersPage />
                </RequireRole>
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/allowance-policy"
            element={
              <ProtectedRoute>
                <RequireRole roles={["administrator"]}>
                  <AllowancePolicyPage />
                </RequireRole>
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<Navigate to="/styles" replace />} />
          <Route path="*" element={<Navigate to="/styles" replace />} />
        </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </BrowserRouter>
  );
}
