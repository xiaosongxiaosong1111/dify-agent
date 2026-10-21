"""Opt-in encrypted login, bound to the same saved Dify origin and version."""
import asyncio,weakref,hashlib
from datetime import datetime,timezone

EMAIL='console_login_email';PASSWORD='console_login_password';BINDING='console_login_binding'
_locks=weakref.WeakKeyDictionary()


def available(store,env):
    binding=env.get(BINDING)
    return (not env.get('console_login_blocked') and isinstance(binding,dict)
            and all(binding.get(k)==env.get(k) for k in ('base_url','version'))
            and isinstance(binding.get('workspace_id'),str) and bool(binding['workspace_id'])
            and binding['workspace_id']==env.get('console_workspace_id')
            and env.get('version')=='1.17.1'
            and store.has_secret(env['id'],EMAIL) and store.has_secret(env['id'],PASSWORD))


async def refresh(client,rejected_token):
    from .dify import DifyError
    store=client.store;env=client.env
    loop=asyncio.get_running_loop();locks=_locks.setdefault(loop,{})
    lock=locks.setdefault((str(store.path.resolve()),env['id']),asyncio.Lock())
    async with lock:
        with store.lock:
            current=store.get('environment',env['id'])
            if not current or any(current.get(k)!=env.get(k) for k in ('base_url','version','connection_revision')):
                raise DifyError('管理连接已变化，未使用已存登录资料；请读取当前环境。')
            if not available(store,current):
                raise DifyError('管理令牌不可用，且此原环境没有已授权保存的登录资料。请在 Sierra 环境中连接一次并选择加密保存。')
            token=store.secret(env['id'],'console_token')
            if token and token!=rejected_token:
                return  # Another caller already replaced this credential.
            email,password=store.secret(env['id'],EMAIL),store.secret(env['id'],PASSWORD)
            secret_stamp=hashlib.sha256((email+'\0'+password).encode()).digest()
            stamp=current.copy()
        try:
            tokens=await client.login(email,password)
            if await client.login_workspace(tokens)!=stamp[BINDING]['workspace_id']:
                raise DifyError('新登录的工作空间与保存授权不同，未替换凭据或派发原操作。')
        except DifyError:
            with store.lock:
                latest=store.get('environment',env['id'])
                if latest==stamp:
                    latest['console_login_blocked']=True
                    store.put('environment',env['id'],latest)
            raise DifyError('自动登录未成功，已暂停此环境的自动登录；没有重试或重发原操作。请核对账号后重新连接。') from None
        finally:
            email=password=''
        with store.lock:
            current=store.get('environment',env['id'])
            latest_secrets=hashlib.sha256((store.secret(env['id'],EMAIL)+'\0'+store.secret(env['id'],PASSWORD)).encode()).digest()
            if (current!=stamp or latest_secrets!=secret_stamp
                    or not available(store,current)):
                raise DifyError('自动登录期间环境或保存授权变化，未替换管理凭据。')
            current['console_auth_mode']='email_password'
            current['console_checked_at']=datetime.now(timezone.utc).isoformat()
            current.setdefault('capabilities',{})['console']='verified'
            store.put_with_secrets('environment',env['id'],current,tokens)
