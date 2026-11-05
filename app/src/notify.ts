import { inDesktopApp } from './tauri'

/** Show an OS notification: Tauri's plugin in the desktop app, the web Notification API in a browser. */
export async function notify(title: string, body: string) {
  try {
    if (inDesktopApp) {
      const n = await import('@tauri-apps/plugin-notification')
      let granted = await n.isPermissionGranted()
      if (!granted) granted = (await n.requestPermission()) === 'granted'
      if (granted) n.sendNotification({ title, body })
    } else if ('Notification' in window) {
      if (Notification.permission === 'default') await Notification.requestPermission()
      if (Notification.permission === 'granted') new Notification(title, { body })
    }
  } catch {
    /* notifications unavailable: the in-app banner still shows */
  }
}
