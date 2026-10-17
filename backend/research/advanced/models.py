"""Small CPU challengers with a shared chronological protocol."""
import numpy as np

def deep_fit(kind,x,y,cal,test,seed=41,epochs=5):
    import torch
    from torch import nn
    torch.manual_seed(seed);torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    class Net(nn.Module):
        def __init__(self):
            super().__init__();n=x.shape[-1]
            if kind=='tcn':self.body=nn.Sequential(nn.Conv1d(n,16,3,padding=2,dilation=1),nn.ReLU(),nn.Conv1d(16,16,3,padding=4,dilation=2),nn.ReLU());self.out=nn.Linear(16,1)
            elif kind=='gru':self.body=nn.GRU(n,16,batch_first=True);self.out=nn.Linear(16,1)
            else:
                self.embed=nn.Linear(n,16);self.position=nn.Parameter(torch.zeros(1,x.shape[1],16));nn.init.normal_(self.position,std=.02)
                self.body=nn.TransformerEncoder(nn.TransformerEncoderLayer(16,2,32,dropout=0,batch_first=True),1,enable_nested_tensor=False);self.out=nn.Linear(16,1)
        def forward(self,z):
            if kind=='tcn':v=self.body(z.transpose(1,2))[:,:,:z.shape[1]][:,:,-1]
            elif kind=='gru':v=self.body(z)[0][:,-1]
            else:v=self.body(self.embed(z)+self.position,mask=torch.triu(torch.full((z.shape[1],z.shape[1]),float('-inf')),diagonal=1))[:,-1]
            return self.out(v).squeeze(-1)
    net=Net();opt=torch.optim.AdamW(net.parameters(),lr=.001,weight_decay=.01);xx=torch.tensor(x,dtype=torch.float32);yy=torch.tensor(y*100,dtype=torch.float32);rng=np.random.default_rng(seed)
    net.train()
    for _ in range(epochs):
        for ids in np.array_split(rng.permutation(len(xx)),max(1,(len(xx)+255)//256)):
            opt.zero_grad();loss=nn.functional.mse_loss(net(xx[ids]),yy[ids]);loss.backward();nn.utils.clip_grad_norm_(net.parameters(),1);opt.step()
    net.eval()
    def pred(z):
        with torch.no_grad():return np.concatenate([net(torch.tensor(v,dtype=torch.float32)).numpy()/100 for v in np.array_split(z,max(1,(len(z)+511)//512))])
    return pred(cal),pred(test),{'parameters':sum(p.numel() for p in net.parameters()),'epochs':epochs,'seed':seed,'device':'cpu','selection':'Fixed architecture and epoch count; test losses never select weights'}

def allocation(method,edges,vol,cov,adv,capital=10000,cap=.1,gross=.8):
    """No leverage/shorts. Cash absorbs residual capacity; no renormalization past caps."""
    from scipy.optimize import minimize
    n=len(edges)
    if not n:return np.zeros(0)
    vol=np.maximum(vol,.005);bounds=np.minimum(cap,np.maximum(0,adv)*.0001/capital)
    if method=='equal':w=np.ones(n)
    elif method in ('inverse_volatility','volatility_target'):w=1/vol
    elif method=='capped_edge':w=np.maximum(edges,0)/vol
    elif method=='risk_parity':
        w=np.ones(n)/n
        for _ in range(60):
            rc=w*(cov@w);target=max(float(w@cov@w),1e-12)/n;w*=np.sqrt(target/np.maximum(rc,1e-12));w/=max(w.sum(),1e-12)
    elif method=='covariance_constrained':
        opt=minimize(lambda z:float(z@cov@z),np.minimum(bounds,gross/n),bounds=list(zip(np.zeros(n),bounds)),constraints=[{'type':'eq','fun':lambda z:z.sum()-min(gross,float(bounds.sum()))}],method='SLSQP',options={'maxiter':100,'ftol':1e-10})
        return np.minimum(bounds,np.maximum(0,opt.x)) if opt.success else np.zeros(n)
    else:raise ValueError('Unknown allocation')
    if w.sum()<=0:return np.zeros(n)
    w=w/w.sum()*gross
    if method=='volatility_target':w*=min(1,.10/np.sqrt(252)/max(np.sqrt(w@cov@w),1e-12))
    return np.minimum(bounds,np.maximum(w,0))

def by_adjust(pvalues,total=None):
    """Benjamini–Yekutieli, including failed/withheld trials as p=1."""
    p=np.asarray(pvalues,float);m=max(len(p),total or 0);harm=sum(1/i for i in range(1,m+1));order=np.argsort(p);q=np.minimum.accumulate((p[order]*m*harm/np.arange(1,len(p)+1))[::-1])[::-1];out=np.empty(len(p));out[order]=np.minimum(q,1);return out.tolist()

def block_test(values,seed=41):
    v=np.asarray(values,float);v=v[np.isfinite(v)]
    if len(v)<20:return {'mean':float(v.mean()) if len(v) else None,'lower':None,'upper':None,'p':1.,'clusters':len(v)}
    rng=np.random.default_rng(seed);n=len(v);length=max(3,round(n**(1/3)));ids=(rng.integers(0,n,(1000,(n+length-1)//length,1))+np.arange(length))%n;means=v[ids.reshape(1000,-1)[:,:n]].mean(axis=1);center=means-v.mean()
    return {'mean':float(v.mean()),'lower':float(np.quantile(means,.025)),'upper':float(np.quantile(means,.975)),'p':float((1+np.sum(np.abs(center)>=abs(v.mean())))/1001),'clusters':n,'block_length':length}
