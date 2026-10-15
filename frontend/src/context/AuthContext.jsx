import { createContext, useContext, useState } from 'react'
import { getToken, setToken } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(getToken())
  const signIn = (t) => { setToken(t); setTokenState(t) }
  const signOut = () => { setToken(null); setTokenState(null) }
  return <AuthContext.Provider value={{ token, signIn, signOut }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
