import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth.jsx'
import Layout from './Layout.jsx'
import AuthPage from './AuthPage.jsx'
import ChatPage from './ChatPage.jsx'
import CollectionsPage from './CollectionsPage.jsx'
import DocumentsPage from './DocumentsPage.jsx'
import StatusPage from './StatusPage.jsx'

function Protected({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<AuthPage />} />
          <Route path="/" element={<Protected><ChatPage /></Protected>} />
          <Route path="/collections" element={<Protected><CollectionsPage /></Protected>} />
          <Route path="/documents" element={<Protected><DocumentsPage /></Protected>} />
          <Route path="/status" element={<Protected><StatusPage /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
