import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from '@/pages/Login'
import Workspace from '@/pages/Workspace'
import Approval from '@/pages/Approval'
import { isAuthenticated, isTokenExpired, getIsAdmin } from '@/lib/auth'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated() || isTokenExpired()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated() || isTokenExpired() || !getIsAdmin()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

/** 路由内容（不含Router，便于测试注入不同Router类型） */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/workspace" element={<ProtectedRoute><Workspace /></ProtectedRoute>} />
      <Route path="/approval" element={<AdminRoute><Approval /></AdminRoute>} />
      <Route path="*" element={<Navigate to="/workspace" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}