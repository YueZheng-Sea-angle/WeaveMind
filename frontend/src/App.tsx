import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLayout } from '@/components/layout/AppLayout'
import { BookLayout } from '@/components/layout/BookLayout'
import { HomePage } from '@/pages/HomePage'
import { ProcessingPage } from '@/pages/ProcessingPage'
import { ChatPage } from '@/pages/ChatPage'
import { ChaptersPage } from '@/pages/ChaptersPage'
import { EntitiesPage } from '@/pages/EntitiesPage'
import { GraphPage } from '@/pages/GraphPage'
import { BookSettingsPage } from '@/pages/BookSettingsPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000 * 30,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/books/:id" element={<BookLayout />}>
              <Route index element={<Navigate to="chat" replace />} />
              <Route path="processing" element={<ProcessingPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chapters" element={<ChaptersPage />} />
              <Route path="entities" element={<EntitiesPage />} />
              <Route path="graph" element={<GraphPage />} />
              <Route path="settings" element={<BookSettingsPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
