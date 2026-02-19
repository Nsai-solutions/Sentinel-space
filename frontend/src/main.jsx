import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    <Toaster
      position="top-right"
      toastOptions={{
        style: {
          background: '#111B2E',
          color: '#E8ECF4',
          border: '1px solid #223052',
          borderRadius: '8px',
          fontFamily: "'Space Grotesk', sans-serif",
          fontSize: '13px',
        },
      }}
    />
  </StrictMode>,
)
