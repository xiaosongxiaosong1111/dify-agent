"""AST-only binding check for Dify's main(**inputs); never evaluate source."""
import ast,inspect

UNKNOWN='Python入口含动态绑定、条件定义或装饰器，调用约定未核实；只能保留静态警告，须在目标沙箱核对。'


class Bindings(ast.NodeVisitor):
    def __init__(self):self.entries=[];self.dynamic=False;self.star_import=False
    def visit_FunctionDef(self,node):
        if node.name=='main':self.entries.append(node)
    visit_AsyncFunctionDef=visit_FunctionDef
    def visit_ClassDef(self,node):
        if node.name=='main':self.entries.append(node)
    def visit_Name(self,node):
        if node.id=='main' and isinstance(node.ctx,(ast.Store,ast.Del)):self.entries.append(node)
    def visit_Import(self,node):
        for alias in node.names:
            if (alias.asname or alias.name.split('.')[0])=='main':self.entries.append(node)
    def visit_ImportFrom(self,node):
        for alias in node.names:
            if alias.name=='*':self.dynamic=True;self.star_import=True
            if (alias.asname or alias.name)=='main':self.entries.append(node)
    def visit_Call(self,node):
        self.dynamic=True;self.generic_visit(node)


def check(code,names):
    errors=[];warnings=[]
    if len(names)!=len(set(names)):errors.append('代码输入变量名重复，无法唯一绑定；请明确每个输入的名称和来源。')
    try:tree=ast.parse(code)
    except (SyntaxError,ValueError,RecursionError):return errors,warnings
    bindings=Bindings();bindings.visit(tree)
    if not bindings.entries:
        if bindings.dynamic:warnings.append(UNKNOWN)
        else:errors.append('Python入口缺少main函数；代码语法可读不代表Dify能调用。')
        return errors,warnings
    entry=bindings.entries[0]
    if bindings.star_import or len(bindings.entries)!=1 or entry not in tree.body or not isinstance(entry,(ast.FunctionDef,ast.AsyncFunctionDef)) or entry.decorator_list:
        warnings.append(UNKNOWN);return errors,warnings
    if isinstance(entry,ast.AsyncFunctionDef):
        errors.append(f'Python入口第{entry.lineno}行是async main；当前平台入口不会等待协程，不能按同步代码节点调用。');return errors,warnings
    args=entry.args;parameters=[];positional=args.posonlyargs+args.args;default_start=len(positional)-len(args.defaults);present=object()
    try:
        for i,arg in enumerate(positional):
            kind=inspect.Parameter.POSITIONAL_ONLY if i<len(args.posonlyargs) else inspect.Parameter.POSITIONAL_OR_KEYWORD
            parameters.append(inspect.Parameter(arg.arg,kind,default=present if i>=default_start else inspect.Parameter.empty))
        if args.vararg:parameters.append(inspect.Parameter(args.vararg.arg,inspect.Parameter.VAR_POSITIONAL))
        for arg,default in zip(args.kwonlyargs,args.kw_defaults):parameters.append(inspect.Parameter(arg.arg,inspect.Parameter.KEYWORD_ONLY,default=present if default is not None else inspect.Parameter.empty))
        if args.kwarg:parameters.append(inspect.Parameter(args.kwarg.arg,inspect.Parameter.VAR_KEYWORD))
        signature=inspect.Signature(parameters)
    except ValueError:
        errors.append(f'Python入口第{entry.lineno}行参数声明不明确或重复，不能绑定节点输入。');return errors,warnings
    try:signature.bind(**dict.fromkeys(names,present))
    except TypeError:
        errors.append(f'Python入口第{entry.lineno}行参数与代码节点输入不匹配；请核对必填、额外及仅位置参数，平台使用main的关键字调用，不会自动改名或补值。')
    return errors,warnings
