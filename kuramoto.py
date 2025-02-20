from numpy import pi
from scipy.fftpack import fft, ifft
import numpy as np

np.seterr(over='raise', invalid='raise')

class KS:
    #
    # Solution of the 1D Kuramoto-Sivashinsky equation
    #
    # u_t + u*u_x + u_xx + u_xxxx = 0,
    # with periodic BCs on x \in [0, 2*pi*L]: u(x+2*pi*L,t) = u(x,t).
    #
    # The nature of the solution depends on the system size L and on the initial
    # condition u(x,0).  Energy enters the system at long wavelengths via u_xx
    # (an unstable diffusion term), cascades to short wavelengths due to the
    # nonlinearity u*u_x, and dissipates via diffusion with u_xxxx.
    #
    # Spatial  discretization: spectral (Fourier)
    # Temporal discretization: exponential time differencing fourth-order Runge-Kutta
    # see AK Kassam and LN Trefethen, SISC 2005

    def __init__(self, L=16, N=128, dt=0.25, nsteps=None, tend=150, iout=1):
        #
        # Initialize
        L  = float(L); dt = float(dt); tend = float(tend)
        if (nsteps is None):
            nsteps = int(tend/dt)
        else:
            nsteps = int(nsteps)
            # override tend
            tend = dt*nsteps
        #
        # save to self
        self.L = L
        self.N = N
        self.dx = 2*pi*L/N
        self.dt = dt
        self.nsteps = nsteps
        self.iout = iout
        self.nout = int(nsteps/iout)
        #
        # set initial condition
        self.IC()
        #
        # initialize simulation arrays
        self.setup_timeseries()
        #
        # precompute Fourier-related quantities
        self.setup_fourier()
        #
        # precompute ETDRK4 scalar quantities:
        self.setup_etdrk4()


    def setup_timeseries(self, nout=None):
        if (nout != None):
            self.nout = int(nout)
        # nout+1 so we store the IC as well
        self.vv = np.zeros([self.nout+1, self.N], dtype=np.complex64)
        self.tt = np.zeros(self.nout+1)
        #
        # store the IC in [0]
        self.vv[0,:] = self.v0
        self.tt[0]   = 0.


    def setup_fourier(self, coeffs=None):
        self.x  = 2*pi*self.L*np.r_[0:self.N]/self.N
        self.k  = np.r_[0:self.N/2, 0, -self.N/2+1:0]/self.L # Wave numbers
        # Fourier multipliers for the linear term Lu
        if (coeffs is None):
            # normal-form equation
            self.l = self.k**2 - self.k**4
        else:
            # altered-coefficients 
            self.l = -      coeffs[0]*np.ones(self.k.shape) \
                     -      coeffs[1]*1j*self.k             \
                     + (1 + coeffs[2])  *self.k**2          \
                     +      coeffs[3]*1j*self.k**3          \
                     - (1 + coeffs[4])  *self.k**4


    def setup_etdrk4(self):
        self.E  = np.exp(self.dt*self.l)
        self.E2 = np.exp(self.dt*self.l/2.)
        self.M  = 16                                           # no. of points for complex means
        self.r  = np.exp(1j*pi*(np.r_[1:self.M+1]-0.5)/self.M) # roots of unity
        self.LR = self.dt*np.repeat(self.l[:,np.newaxis], self.M, axis=1) + np.repeat(self.r[np.newaxis,:], self.N, axis=0)
        self.Q  = self.dt*np.real(np.mean((np.exp(self.LR/2.) - 1.)/self.LR, 1))
        self.f1 = self.dt*np.real( np.mean( (-4. -    self.LR              + np.exp(self.LR)*( 4. - 3.*self.LR + self.LR**2) )/(self.LR**3) , 1) )
        self.f2 = self.dt*np.real( np.mean( ( 2. +    self.LR              + np.exp(self.LR)*(-2. +    self.LR             ) )/(self.LR**3) , 1) )
        self.f3 = self.dt*np.real( np.mean( (-4. - 3.*self.LR - self.LR**2 + np.exp(self.LR)*( 4. -    self.LR             ) )/(self.LR**3) , 1) )
        self.g  = -0.5j*self.k


    def IC(self, u0=None, v0=None, testing=False):
        #
        # Set initial condition, either provided by user or by "template"
        if (v0 is None):
            # IC provided in u0 or use template
            if (u0 is None):
                # set u0
                if testing:
                    # template from AK Kassam and LN Trefethen, SISC 2005
                    u0 = np.cos(self.x/self.L)*(1. + np.sin(self.x/self.L))
                else:
                    # random noise
                    u0 = (np.random.rand(self.N) -0.5)*0.01
            else:
                # check the input size
                if (np.size(u0,0) != self.N):
                    print('Error: wrong IC array size')
                    return -1
                else:
                    # if ok cast to np.array
                    u0 = np.array(u0)
            # in any case, set v0:
            v0 = fft(u0)
        else:
            # the initial condition is provided in v0
            # check the input size
            if (np.size(v0,0) != self.N):
                print('Error: wrong IC array size')
                return -1
            else:
                # if ok cast to np.array
                v0 = np.array(v0)
                # and transform to physical space
                u0 = ifft(v0)
        #
        # and save to self
        self.u0  = u0
        self.v0  = v0
        self.v   = v0
        self.t   = 0.
        self.stepnum = 0
        self.ioutnum = 0 # [0] is the initial condition
        

    def step(self):
        #
        # Computation is based on v = fft(u), so linear term is diagonal.
        # The time-discretization is done via ETDRK4
        # (exponential time differencing - 4th order Runge Kutta)
        #
        v = self.v;                           Nv = self.g*fft(np.real(ifft(v))**2)
        a = self.E2*v + self.Q*Nv;            Na = self.g*fft(np.real(ifft(a))**2)
        b = self.E2*v + self.Q*Na;            Nb = self.g*fft(np.real(ifft(b))**2)
        c = self.E2*a + self.Q*(2.*Nb - Nv);  Nc = self.g*fft(np.real(ifft(c))**2)
        #
        self.v = self.E*v + Nv*self.f1 + 2.*(Na + Nb)*self.f2 + Nc*self.f3
        self.stepnum += 1
        self.t       += self.dt


    def simulate(self, nsteps=None, iout=None, restart=False, correction=[]):
        #
        # If not provided explicitly, get internal values
        if (nsteps is None):
            nsteps = self.nsteps
        else:
            nsteps = int(nsteps)
            self.nsteps = nsteps
        if (iout is None):
            iout = self.iout
            nout = self.nout
        else:
            self.iout = iout
        if restart:
            # update nout in case nsteps or iout were changed
            nout      = int(nsteps/iout)
            self.nout = nout
            # reset simulation arrays with possibly updated size
            self.setup_timeseries(nout=self.nout)
        #
        # advance in time for nsteps steps
        if (correction==[]):
            for n in range(1,self.nsteps+1):
                try:
                    self.step()
                except FloatingPointError:
                    #
                    # something exploded
                    # cut time series to last saved solution and return
                    self.nout = self.ioutnum
                    self.vv.resize((self.nout+1,self.N)) # nout+1 because the IC is in [0]
                    self.tt.resize(self.nout+1)          # nout+1 because the IC is in [0]
                    return -1
                if ( (self.iout>0) and (n%self.iout==0) ):
                    self.ioutnum += 1
                    self.vv[self.ioutnum,:] = self.v
                    self.tt[self.ioutnum]   = self.t
        else:
            # lots of code duplication here, but should improve speed instead of having the 'if correction' at every time step
            for n in range(1,self.nsteps+1):
                try:
                    self.step()
                    self.v += correction
                except FloatingPointError:
                    #
                    # something exploded
                    # cut time series to last saved solution and return
                    self.nout = self.ioutnum
                    self.vv.resize((self.nout+1,self.N)) # nout+1 because the IC is in [0]
                    self.tt.resize(self.nout+1)          # nout+1 because the IC is in [0]
                    return -1
                if ( (self.iout>0) and (n%self.iout==0) ):
                    self.ioutnum += 1
                    self.vv[self.ioutnum,:] = self.v
                    self.tt[self.ioutnum]   = self.t

        self.fou2real()


    def fou2real(self):
        #
        # Convert from spectral to physical space
        self.uu = np.real(ifft(self.vv))




