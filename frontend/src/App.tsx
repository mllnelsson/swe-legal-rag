import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";

import { AgentPage } from "./features/agent/AgentPage";
import { AppShell } from "./components/layout/AppShell";
import {
  ConceptDocumentsRoute,
  ConceptIndexRoute,
  KeywordDocumentsRoute,
  KeywordIndexRoute,
} from "./features/browse/routes";
import { DecisionPage } from "./features/decision/DecisionPage";
import { ResultsPage } from "./features/search/ResultsPage";
import { SearchHomePage } from "./features/search/SearchHomePage";
import { StylePage } from "./features/style/StylePage";

// The corpus only changes when the ingestion pipeline runs, and nothing in this
// app writes. Refetching on focus would spend a local embedding pass to return
// the same rows.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1, staleTime: Infinity },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<SearchHomePage />} />
            <Route path="sok" element={<ResultsPage />} />
            <Route path="agent" element={<AgentPage />} />
            <Route path="beslut/:documentId" element={<DecisionPage />} />
            <Route path="sokord" element={<KeywordIndexRoute />} />
            <Route path="sokord/:entityId" element={<KeywordDocumentsRoute />} />
            <Route path="begrepp" element={<ConceptIndexRoute />} />
            <Route path="begrepp/:entityId" element={<ConceptDocumentsRoute />} />
            {/* Dev reference, not linked from the app's navigation. */}
            <Route path="stil" element={<StylePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
