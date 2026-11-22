import { useCallback, useState } from "react";
import { clearSession, getToken } from "./api";
import { Console } from "./Console";
import { Login } from "./Login";

export function App() {
  const [authed, setAuthed] = useState(() => Boolean(getToken()));
  const logout = useCallback(() => {
    clearSession();
    setAuthed(false);
  }, []);

  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;
  return <Console onLogout={logout} />;
}
