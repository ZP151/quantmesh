import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

// QuantMesh is a dark-technical product (PRODUCT.md); the class also
// sits on <html> in index.html so the first paint is already dark.
document.documentElement.classList.add('dark')

// The FastAPI server hosts the bundle under /app (ADR-0013 decision 2);
// the router lives on that base so deep links like /app/markets resolve
// to their routes instead of the catch-all NotFound.
const ROUTER_BASE = '/app'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={ROUTER_BASE}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
