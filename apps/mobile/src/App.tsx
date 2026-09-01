/**
 * App root.
 *
 * Provider order matters here. Connectivity sits inside Auth because a drain
 * uploads with the signed-in user's token; it sits outside the navigator so
 * the queue keeps draining while the operator is on any screen -- including
 * the camera, which is exactly where captures are being made.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider } from "./auth/auth-context";
import { ConnectivityProvider } from "./net/connectivity";
import { RootNavigator } from "./navigation";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A field phone's connection comes and goes. Retrying once absorbs a
      // single dropped request; retrying four times just delays the error
      // message the operator needs in order to move.
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ConnectivityProvider>
            <StatusBar style="light" />
            <RootNavigator />
          </ConnectivityProvider>
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
