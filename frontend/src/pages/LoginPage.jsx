import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

export default function LoginPage() {
  const { register, handleSubmit, formState: { errors, isSubmitting }, setError } = useForm()
  const { signIn } = useAuth()
  const navigate = useNavigate()

  const onSubmit = async ({ username, password }) => {
    try {
      const { access_token } = await login(username, password)
      signIn(access_token)
      navigate('/pay')
    } catch (e) {
      setError('root', { message: e.message })
    }
  }

  return (
    <main className="min-h-screen grid place-items-center bg-slate-50">
      <form onSubmit={handleSubmit(onSubmit)} className="w-full max-w-sm bg-white p-6 rounded-xl shadow space-y-4">
        <h1 className="text-xl font-semibold">iBanking - Sign in</h1>
        <input className="w-full border rounded p-2" placeholder="Username" {...register('username', { required: true })} />
        <input className="w-full border rounded p-2" type="password" placeholder="Password" {...register('password', { required: true })} />
        {errors.root && <p className="text-red-600 text-sm">{errors.root.message}</p>}
        <button disabled={isSubmitting} className="w-full bg-blue-600 text-white rounded p-2 disabled:opacity-50">Sign in</button>
      </form>
    </main>
  )
}
