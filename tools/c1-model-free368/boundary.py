"""Additional fail-closed limits for a future approved runner; no HTTP or live entry."""
from urllib.parse import urlsplit
from guard import Boundary,require


class ModelFreeBoundary(Boundary):
    limits={'reads':28,'login':1,'import':1,'publish':1,'key':1,'run':2}
    phases={'reconnect','modified_import','modified_publish','modified_key','modified_hit','modified_miss'}

    def admit(self,request):
        require(str(request.url)!=self.provider['base_url'].rstrip('/')+'/chat/completions','New model requests forbidden')
        actual=urlsplit(str(request.url));target=urlsplit(self.env['base_url'])
        require((actual.scheme,actual.netloc)==(target.scheme,target.netloc),'Model and foreign origins forbidden')
        require(self.record.get('phase') in self.phases,'Only the model-free remaining phases are allowed')
        kind=None
        if request.method=='GET':kind='reads'
        elif request.method=='POST':
            if actual.path=='/console/api/login':kind='login'
            elif actual.path=='/console/api/apps/imports':kind='import'
            elif actual.path.endswith('/workflows/publish'):kind='publish'
            elif actual.path.endswith('/api-keys'):kind='key'
            elif actual.path=='/v1/workflows/run':kind='run'
        # Check tighter cumulative caps before the existing validator changes counters.
        if kind is not None:require(self.counts[kind]<self.limits[kind],'Model-free remaining dispatch cap reached')
        return super().admit(request)
