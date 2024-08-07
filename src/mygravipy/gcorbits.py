import numpy as np
import matplotlib.pyplot as plt
import logging
import glob
import re
from astropy import units as u
from astropy.visualization import make_lupton_rgb
from astropy import constants as c
from scipy.optimize import newton
from scipy.special import j1
from datetime import datetime
from pkg_resources import resource_filename

from .utils import *
from .star_orbits import star_pms, star_orbits

deg_to_rad = np.pi/180
microarcsec_to_deg = (10**(-3))/3600

class GCorbits():
    def __init__(self, t=None, loglevel='INFO'):
        """
        Package to get positions of stars at a certain point in time
        Orbits and proper motions from Stefan
        Does not contain GR effects and orbits are not necessarily up to date

        Supress outputs with verbose=False

        Main functions:
        plot_orbits : plot the stars for a given time
        pos_orbit : get positions for stars with orbits
        pos_pm : get positions for stars with proper motions
        """
        log_level = log_level_mapping.get(loglevel, logging.INFO)
        self.gcorb_logger = logging.getLogger(__name__)
        self.gcorb_logger.setLevel(log_level)

        if t is None:
            d = datetime.utcnow()
            t = d.strftime("%Y-%m-%dT%H:%M:%S")
        if isinstance(t, float):
            pass
        else:
            if isinstance(t, str) and len(t) == 10:
                t += 'T12:00:00'
            try:
                t = convert_date(t)[0]
            except ValueError:
                raise ValueError('t has to be given as YYYY-MM-DDTHH:MM:SS, YYYY-MM-DD, or float')
        self.t = t
        self.star_poly = {}
        self.poly_stars = []
        self.star_orbits = {}
        self.orbit_stars = []
        self.star_pms = {}
        self.pm_stars = []

        _s = resource_filename(__name__, f'Datafiles/s*.dat')
        dfiles = sorted(glob.glob(_s))

        for d in dfiles:
            _d = d[-8:-4]
            snum = int(_d[_d.find('/s')+2:])
            _data = []
            with open(d, 'r') as file:
                for line in file:
                    # Process each line
                    l = line.strip()
                    l = l.replace('\t', ' ')
                    if l == '; position data date RA delta RA DEC delta DEC':
                        break
                    _data.append(l)

            # Check for polynomial
            ra_s = None
            de_s = None
            for _s in _data:
                if 'polyFitResultRA' in _s:
                    ra_s = _s
                elif 'polyFitResultDec' in _s:
                    de_s = _s
            if ra_s is not None and de_s is not None:
                self.gcorb_logger.debug(f'Polynomial found for S{snum}')
                
                ra = [float(m) for m in re.findall(r'-?\d+\.\d+', ra_s)]
                de = [float(m) for m in re.findall(r'-?\d+\.\d+', de_s)]
                tref = ra[0]
                ra = ra[1:]
                de = de[1:]
                npol = (len(ra))//2
                
                s = {'name': f'S{snum}',
                     'type': '',
                     'Kmag': 20,
                     'ra': ra,
                     'de': de,
                     'tref': tref,
                     'npol': npol}
                self.star_poly[f'S{snum}'] = s
                self.poly_stars.append(f'S{snum}')
            
            # Check for orbit
            else:
                sdx = -1
                for _sdx, _s in enumerate(_data):
                    if _s == '; best fitting orbit paramters':
                        sdx = _sdx + 1
                        break
                if sdx == -1:
                    self.gcorb_logger.warning(f'No orbit or polynomial found for S{snum}')
                    continue          
                data_new = []
                for _s in _data[sdx:]:
                    data_new.append(_s[:_s.find(' ; ')])
                data_new = [
                    [float(m) for m in re.findall(r'-?\d+(?:\.\d+)?', line)][0]
                     for line in data_new]
                data_new = np.array(data_new)
                
                if len(data_new) != 14:
                    self.gcorb_logger.debug(f'No orbit or polynomial found for S{snum}')
                    continue

                s = {'name': f'S{snum}',
                     'type': '',
                     'a': data_new[0]*1e3,
                     'e': data_new[1],
                     'P': data_new[2],
                     'T': data_new[3],
                     'i': data_new[4]/180*np.pi,
                     'CapitalOmega': data_new[5]/180*np.pi,
                     'Omega': data_new[6]/180*np.pi,
                     'Kmag': 20,
                     'type': ''}
                self.gcorb_logger.debug(f'Orbit found for S{snum}')
                self.star_orbits[f'S{snum}'] = s
                self.orbit_stars.append(f'S{snum}')
                

        for s in star_orbits:
            if s['name'] in self.star_orbits:
                self.star_orbits[s['name']]['type'] = s['type']
                self.star_orbits[s['name']]['Kmag'] = s['Kmag']
            else:
                self.star_orbits[s['name']] = s
                self.orbit_stars.append(s['name'])
                self.gcorb_logger.debug(f'Added {s["name"]} from old orbits')

        for s in star_pms:
            if s['name'] in self.star_orbits:
                self.star_orbits[s['name']]['type'] = s['type']
                self.star_orbits[s['name']]['Kmag'] = s['Kmag']
            elif s['name'] in self.star_poly:
                self.star_poly[s['name']]['type'] = s['type']
                self.star_poly[s['name']]['Kmag'] = s['Kmag']
            else:
                self.star_pms[s['name']] = s
                self.pm_stars.append(s['name'])
                self.gcorb_logger.debug(f'Added {s["name"]} from old pm stars')

        self.gcorb_logger.info(f'Evaluating for {t:.4f}')
        self.gcorb_logger.debug('Stars with orbits:')
        self.gcorb_logger.debug(self.orbit_stars)
        self.gcorb_logger.debug('')
        self.gcorb_logger.debug('Stars with polynomias:')
        self.gcorb_logger.debug(self.poly_stars)
        self.gcorb_logger.debug('')
        self.gcorb_logger.debug('Stars with proper motions:')
        self.gcorb_logger.debug(self.pm_stars)


        # calculate starpos
        starpos = []
        starpos.append(['SGRA', 0, 0, '', 15.7])
        for star in self.star_orbits:
            _s = self.star_orbits[star]
            x, y = self.pos_orbit(star)
            starpos.append([_s['name'], x*1000, y*1000,
                            _s['type'], _s['Kmag']])
        for star in self.star_poly:
            _s = self.star_poly[star]
            x, y = self.pos_poly(star)
            starpos.append([_s['name'], x*1000, y*1000, _s['type'], _s['Kmag']])
        for star in self.star_pms:
            _s = self.star_pms[star]
            x, y = self.pos_pm(star)
            starpos.append([_s['name'], x*1000, y*1000, _s['type'], _s['Kmag']])
        self.starpos = starpos


    def star_pos(self, star):
        try:
            return self.pos_orbit(star)
        except KeyError:
            try:
                return self.pos_poly(star)
            except KeyError:
                return self.pos_pm(star)

    def star_kmag(self, star):
        try:
            return self.star_orbits[star]['Kmag']
        except KeyError:
            try:
                return self.star_poly[star]['Kmag']
            except KeyError:
                return self.star_pms[star]['Kmag']

    def pos_poly(self, star):
        t = self.t
        star = self.star_poly[star]

        res = [0, 0]
        for p in range(star['npol']):
            res[0] += star['ra'][p*2]*(t - star['tref'])**p
            res[1] += star['de'][p*2]*(t - star['tref'])**p
        
        return np.array(res)


    def pos_orbit(self, star, rall=False):
        """
        Calculates the position of a star with known orbits
        star: has to be in the list: orbit_stars
        time: the time of evaluation, in float format 20xx.xx
        rall: if true returns also z-position
        """
        t = self.t
        star = self.star_orbits[star]

        M0 = 4.40
        R0 = 8.34
        m_unit = M0*1e6*u.solMass
        a_unit = u.arcsec
        t_unit = u.yr

        l_unit = a_unit.to(u.rad)*(R0*u.kpc)
        G = float(c.G.cgs * m_unit*t_unit**2/l_unit**3)
        mu = G
        a = star['a']/1000
        n = self.mean_motion(mu, a)
        M = self.mod2pi(n*(t-star['T']))
        f = self.true_anomaly(star['e'], M)

        r = a*(1-star['e']*star['e'])/(1+star['e']*np.cos(f))
        # v = np.sqrt(mu/a/(1-star['e']**2))

        cO = np.cos(star['CapitalOmega'])
        sO = np.sin(star['CapitalOmega'])
        co = np.cos(star['Omega'])
        so = np.sin(star['Omega'])
        cf = np.cos(f)
        sf = np.sin(f)
        ci = np.cos(star['i'])
        si = np.sin(star['i'])

        x = r*(sO*(co*cf-so*sf)+cO*(so*cf+co*sf)*ci)
        y = r*(cO*(co*cf-so*sf)-sO*(so*cf+co*sf)*ci)
        z = r*(so*cf+co*sf)*si

        if rall:
            return np.array([x, y, z])
        else:
            return np.array([x, y])

    def pos_pm(self, star):
        """
        Calculates the position of a star with proper motion
        star: has to be in the list: pm_stars
        """
        t = self.t
        star = self.star_pms[star]
        vx = star['vx']/1000
        vy = star['vy']/1000
        x = star['x']/1000
        y = star['y']/1000

        x = x+vx*(t-star['T'])
        y = y+vy*(t-star['T'])
        if star['ax'] != 0:
            ax = star['ax']/1000
            x += ax/2*(t-star['T'])**2
            vx += ax*(t-star['T'])
        if star['ay'] != 0:
            ay = star['ay']/1000
            y += ay/2*(t-star['T'])**2
            vy += ay*(t-star['T'])
        return np.array([-x, y])

    def true_anomaly(self, e, M):
        E = self.eccentric_anomaly(e, M)
        if e > 1:
            return 2*np.arctan(np.sqrt((1+e)/(e-1))*np.tanh(E/2))
        else:
            return 2*np.arctan(np.sqrt((1+e)/(1-e))*np.tan(E/2))

    def mean_motion(self, mu, a):
        return np.sign(a) * np.sqrt(np.fabs(mu/a**3))

    def mod2pi(self, x):
        return (x+np.pi) % (2*np.pi) - np.pi

    def eccentric_anomaly(self, e, M, *args, **kwargs):
        if e < 1:
            f = lambda E: E - e*np.sin(E) - M
            fp = lambda E: 1 - e*np.cos(E)
            E0 = M if e < 0.8 else np.sign(M)*np.pi
            E = self.mod2pi(newton(f, E0, fp, *args, **kwargs))
        else:
            f = lambda E: E - e*np.sinh(E) - M
            fp = lambda E: 1 - e*np.cosh(E)
            E0 = np.sign(M) * np.log(2*np.fabs(M)/e+1.8)
            E = newton(f, E0, fp, *args, **kwargs)
        return E

    def find_stars(self, x, y, fiberrad=70, plot=False, plotlim=400):
        """
        find all stars whcih are within one fiberad from x, y
        returns a list of stars
        if plot is True, plots the stars in the inner region
        plotlim: radius of the plot
        """
        self.gcorb_logger.info(f'Finding stars within {fiberrad} mas from {x}, {y}')
        starpos = self.starpos
        stars = []
        for s in starpos:
            n, sx, sy, _, mag = s
            dist = np.sqrt((sx-x)**2+(sy-y)**2)
            if dist < fiberrad:
                dmag = -2.5*np.log10(fiber_coupling(dist))
                stars.append([n, sx-x, sy-y, dist, mag, mag + dmag])
                self.gcorb_logger.info(f'{n} at a distance of [{sx-x:.2f} {sy-y:.2f}] from fiber pointing')

        if plot:
            fig, ax = plt.subplots()
            for s in starpos:
                n, sx, sy, _, _ = s
                if np.any(np.abs(sx) > plotlim) or np.any(np.abs(sy) > plotlim):
                    continue
                color = 'grey'
                # check if n in stars[:,0]
                for s in stars:
                    if n == s[0]:
                        color = 'C0'
                plt.scatter(sx, sy, c=color, s=7)
                plt.text(sx-3, sy, '%s' % (n), fontsize=5, color=color)
            plt.axis([plotlim*1.2, -plotlim*1.2,
                      -plotlim*1.2, plotlim*1.2])
            circ = plt.Circle([x, y], radius=fiberrad, facecolor="None",
                            edgecolor='C0', linewidth=0.2)
            ax.add_artist(circ)
            plt.gca().set_aspect('equal', adjustable='box')
            plt.xlabel('dRa [mas]')
            plt.ylabel('dDec [mas]')
            plt.show()
        return stars, starpos

    def star_pos_list(self, offs=[0,0], lim=70):
        """
        Returns a list of stars within the fiber radius
        """
        starpos = self.starpos
        stars = []
        for s in starpos:
            n, sx, sy, _, mag = s
            dist = np.sqrt((sx-offs[0])**2+(sy-offs[1])**2)
            if dist < lim:
                dmag = -2.5*np.log10(fiber_coupling(dist))
                stars.append([n, sx-offs[0], sy-offs[1], dist, mag, mag + dmag])
        return stars
    
    def flux_ratio(self, mag1, mag2):
        """
        Returns the flux ratio from two stars in magnitudes
        """
        return 10**((mag1-mag2)/2.5)


    def plot_orbits(self, off=[0, 0], t=None, figsize=8, lim=100, long=False):
        """
        Plot the inner region around SgrA* at a given TIME
        lim:  radius to which stars are plotted
        long: more information if True
        """
        starpos = self.starpos
        fig, ax = plt.subplots()
        fig.set_figheight(figsize)
        fig.set_figwidth(figsize)
        for s in starpos:
            n, x, y, ty, mag = s
            if np.any(np.abs(x-off[0]) > lim) or np.any(np.abs(y-off[1]) > lim):
                continue
            if long:
                if ty == 'e':
                    plt.scatter(x, y, c='C2', s=10)
                    plt.text(x-3, y, '%s m$_K$=%.1f' % (n, mag), fontsize=6,
                             color='C2')
                elif ty == 'l':
                    plt.scatter(x, y, c='C0', s=10)
                    plt.text(x-3, y, '%s m$_K$=%.1f' % (n, mag), fontsize=6,
                             color='C0')
                else:
                    plt.scatter(x, y, c='C1', s=10)
                    plt.text(x-3, y, '%s m$_K$=%.1f' % (n, mag), fontsize=6,
                             color='C1')
            else:
                if ty == 'e':
                    plt.scatter(x, y, c='C2', s=10)
                    plt.text(x-3, y, '%s' % (n), fontsize=6, color='C2')
                elif ty == 'l':
                    plt.scatter(x, y, c='C0', s=10)
                    plt.text(x-3, y, '%s' % (n), fontsize=6, color='C0')
                else:
                    plt.scatter(x, y, c='C1', s=10)
                    plt.text(x-3, y, '%s' % (n), fontsize=6, color='C1')

        plt.axis([lim*1.2+off[0], -lim*1.2+off[0],
                  -lim*1.2+off[1], lim*1.2+off[1]])
        plt.gca().set_aspect('equal', adjustable='box')

        fiberrad = 70
        circ = plt.Circle((off), radius=fiberrad, facecolor="None",
                          edgecolor='darkblue', linewidth=0.2)
        ax.add_artist(circ)
        plt.text(0+off[0], -78+off[1], 'GRAVITY Fiber FoV', fontsize='6', color='darkblue',
                 ha='center')
        if np.any(np.abs(off[0]) > lim) or np.any(np.abs(off[1]) > lim):
            pass
        else:
            plt.scatter(0, 0, color='k', s=20, zorder=100)
            plt.text(-4, -8, 'Sgr A*', fontsize='8')

        if off != [0,0]:
            plt.scatter(*off, color='k', marker='X', s=20, zorder=100)
            plt.text(-4+off[0], -8+off[1], 'Pointing*', fontsize='8')

        plt.text(-80+off[0], 100+off[1], 'late type', fontsize=6, color='C0')
        plt.text(-80+off[0], 92+off[1], 'early type', fontsize=6, color='C2')
        plt.text(-80+off[0], 84+off[1], 'unknown', fontsize=6, color='C1')

        plt.xlabel('dRa [mas]')
        plt.ylabel('dDec [mas]')
        plt.show()


    #Add stars to a given image
    def add_stars(self, x, y, coord, mag, ka):
        """
        Returns a simulated image of a single star as observed from a 
        telescope.

        Parameters
        ----------
        x : meshgrid
            sky coordinates (RA)
        y : meshgrid
            sky coordinates (DEC)
        coord : array
            Star coordinates
        mag : float
            Star magnitude
        ka : float
            wavelength of light divided by the telescope aperture

        Returns
        -------
        array
            Simulated image to be displayed with imshow
        """

        #Get star coordinates 
        xc = coord[0]
        yc = coord[1]

        #Get magnitude
        I0 = np.exp(17-mag)
        
        #Add airy disk
        theta = np.sqrt(((x-xc))**2 + (y-yc)**2)*microarcsec_to_deg*deg_to_rad
        arg = ka*theta

        imag = I0*( 2*j1(arg) / arg)**2

        return imag



    def mock_observation(self, 
                         off= [0, 0],
                         figsize=5, 
                         lim=100, 
                         long=False,
                         plot_fiber=False,
                         fiber_text=False,
                         telescope_size=130,
                         wavelength=1.65*10**(-6),
                         npixels=1000,
                         savefig=False,
                         figname='test.png'):
        """
        Plot the inner region around SgrA* at a given TIME simulating 
        a telescope
        lim:  radius to which stars are plotted
        long: more information if True
        """
        #Calculate the wavenumber of the diffraction pattern
        ka = 2*np.pi*telescope_size/wavelength  # (2*pi/l) * D
        starpos = self.starpos
        
        fig, ax  = plt.subplots(figsize=(figsize, figsize), dpi=300)
        ax.axis([lim*1.2+off[0], -lim*1.2+off[0],
                 -lim*1.2+off[1], lim*1.2+off[1]])
        ax.set_aspect('equal')
        ax.set_xlabel('dRa [mas]')
        ax.set_ylabel('dDec [mas]')
        ax.grid(False)

        xlist, ylist = np.meshgrid(
                np.linspace(lim*1.2+off[0], -lim*1.2+off[0], npixels), 
                np.linspace(-lim*1.2+off[1], lim*1.2+off[1], npixels))

        early_type_image = 0*xlist
        late_type_image = 0*xlist
        no_type_image = 0*xlist

        et_color = np.array([52, 207, 235])/256     # Early type (Blue)
        lt_color = np.array([235, 131, 52])/256      # Late type (Red)
        nt_color = np.array([256, 256, 256])/256     # No type (white)

        for s in starpos:
            n, xc, yc, ty, mag = s
            #If star is outside of the field of view, continue to next star            
            if np.any(np.abs(xc-off[0]) > lim) or np.any(np.abs(yc-off[1]) > lim):
                continue
            
            if long:
                if ty == 'e':
                    early_type_image += self.add_stars(xlist, 
                                                       ylist, 
                                                       [-xc,yc], 
                                                       mag, ka) 
                    xlabel = -xc-20*lim/500
                    ylabel =  yc+20*lim/500
                    if np.any(np.abs( xlabel - off[0]) < lim) or np.any(np.abs(ylabel-off[1]) < lim):                        
                        ax.annotate('%s m$_K$=%.1f' % (n, mag), 
                                    xy=(xc,yc),
                                    xytext=(-xc-20*lim/500,yc+20*lim/500),
                                    rotation=0, 
                                    fontsize=6.5,
                                    ha='left', va='bottom', color=et_color)
                    
                elif ty == 'l':
                    late_type_image += self.add_stars(xlist, 
                                                      ylist, 
                                                      [-xc,yc], 
                                                      mag, ka) 
                    
                    ax.annotate('%s m$_K$=%.1f' % (n, mag), 
                                xy=(xc, yc),
                                xytext=(xc-20*lim/500,yc+20*lim/500),
                                rotation=0, 
                                fontsize=6.5,
                                ha='left', va='bottom', color=lt_color)
        
                else:
                    no_type_image += self.add_stars(xlist, 
                                                    ylist, 
                                                    [-xc,yc], 
                                                    mag, ka)               
                    
                    ax.annotate('%s m$_K$=%.1f' % (n, mag), 
                                xy=(xc,yc),
                                xytext=(xc-20*lim/500,yc+20*lim/500),
                                rotation=0, 
                                fontsize=6.5,
                                ha='left', va='bottom', color=nt_color)
        

            else:
                if ty == 'e':
                    early_type_image += self.add_stars(xlist, 
                                                      ylist, 
                                                      [-xc,yc], 
                                                      mag, ka) 
                    xlabel = -xc-20*lim/500
                    ylabel =  yc+20*lim/500

                    if np.any(np.abs( xlabel + off[0]) < 1.02*lim) and np.any(np.abs(ylabel-off[1]) < 1.02*lim):
                        ax.annotate('%s' % (n), 
                                    xy=(xc,yc),
                                    xytext=(xc-20*lim/500,yc+20*lim/500),
                                    rotation=0, 
                                    fontsize=6.5,
                                    ha='left', va='bottom', color=et_color)
                    
                elif ty == 'l':                    
                    late_type_image += self.add_stars(xlist, 
                                                      ylist, 
                                                      [-xc,yc], 
                                                      mag, ka) 
                    xlabel = -xc-20*lim/500
                    ylabel =  yc+20*lim/500

                    if np.any(np.abs( xlabel + off[0]) < 1.02*lim) and np.any(np.abs(ylabel-off[1]) < 1.02*lim):
                        ax.annotate('%s' % (n), 
                                    xy=(xc,yc),
                                    xytext=(xc-20*lim/500,yc+20*lim/500),
                                    rotation=0, 
                                    fontsize=6.5,
                                    ha='left', va='bottom', color=lt_color)

                else:
                    if n == 'SGRA':
                        continue

                    no_type_image += self.add_stars(xlist, 
                                                    ylist, 
                                                    [-xc,yc], 
                                                    mag, ka)               
                    
                    xlabel = -xc-20*lim/500
                    ylabel =  yc+20*lim/500

                    if (np.abs( xlabel + off[0]) < 1.02*lim) and (np.abs(ylabel-off[1]) < 1.02*lim) :
                        ax.annotate('%s' % (n), 
                                    xy=(-xc,yc),
                                    xytext=(xc-20*lim/500,yc+20*lim/500),
                                    rotation=0, 
                                    fontsize=6.5,
                                    ha='left', va='bottom', color=nt_color)
            
        if plot_fiber:
            fiberrad = 70
            circ = plt.Circle((off), 
                              radius=fiberrad, facecolor="None",
                              edgecolor='red', linewidth=0.5, ls='--')
            ax.add_artist(circ)
        
            if fiber_text:
                ax.text(   0+off[0], -78+off[1], 'GRAVITY Fiber FoV', 
                            fontsize='6', 
                            color='red',
                            ha='center')   

        #If the fiber offset is off the plotting limits, ignore the SgA point
        if np.any(np.abs(off[0]) > lim) or np.any(np.abs(off[1]) > lim):
            pass
        else:
            ax.scatter(0, 0, color='yellow', s=2, lw=0.2, zorder=100, marker='x')
            ax.text(-4, -8, 'Sgr A*', fontsize='6', color=nt_color)

        #If not directly poiting at SgA, make a legend
        if off != [0,0]:
            ax.scatter(*off, color='k', marker='X', s=20, zorder=100)
            ax.text(-4+off[0], -8+off[1], 'Pointing*', fontsize='8')

        #Plot Legend
        ax.annotate('Late type', xy=(0.99, 0.01), rotation=0, fontsize=6.5, xycoords='axes fraction', ha='right', va='bottom', color=lt_color)
        ax.annotate('Early type', xy=(0.99, 0.04), rotation=0, fontsize=6.5, xycoords='axes fraction', ha='right', va='bottom', color=et_color)
        ax.annotate('Unknown', xy=(0.99, 0.07), rotation=0, fontsize=6.5, xycoords='axes fraction', ha='right', va='bottom', color=nt_color)

        ax.annotate(ty[:10], 
                    xy=(0.01,0.99), 
                    rotation=0, 
                    fontsize=6.5, 
                    xycoords='axes fraction', 
                    ha='left', 
                    va='top', 
                    color='white')


        r = nt_color[0]*no_type_image + lt_color[0]*late_type_image + et_color[0]*early_type_image
        g = nt_color[1]*no_type_image + lt_color[1]*late_type_image + et_color[1]*early_type_image
        b = nt_color[2]*no_type_image + lt_color[2]*late_type_image + et_color[2]*early_type_image

        rgb = make_lupton_rgb(r, g, b, Q=10, stretch=0.05)

        ax.imshow(rgb,
                  extent =[xlist.min(), xlist.max(), ylist.min(), ylist.max()],
                  origin ='lower')

        #Save or display?
        if savefig:
            fig.savefig(figname)
        else:
            plt.show()

        plt.close(fig)
        '''
        plt.axis([lim*1.2+off[0], -lim*1.2+off[0],
                  -lim*1.2+off[1], lim*1.2+off[1]])
        plt.gca().set_aspect('equal', adjustable='box')

        fiberrad = 70
        circ = plt.Circle((off), radius=fiberrad, facecolor="None",
                          edgecolor='darkblue', linewidth=0.2)
        ax.add_artist(circ)
        plt.text(0+off[0], -78+off[1], 'GRAVITY Fiber FoV', fontsize='6', color='darkblue',
                 ha='center')
        if np.any(np.abs(off[0]) > lim) or np.any(np.abs(off[1]) > lim):
            pass
        else:
            plt.scatter(0, 0, color='k', s=20, zorder=100)
            plt.text(-4, -8, 'Sgr A*', fontsize='8')

        if off != [0,0]:
            plt.scatter(*off, color='k', marker='X', s=20, zorder=100)
            plt.text(-4+off[0], -8+off[1], 'Pointing*', fontsize='8')

        plt.text(-80+off[0], 100+off[1], 'late type', fontsize=6, color='C0')
        plt.text(-80+off[0], 92+off[1], 'early type', fontsize=6, color='C2')
        plt.text(-80+off[0], 84+off[1], 'unknown', fontsize=6, color='C1')

        plt.xlabel('dRa [mas]')
        plt.ylabel('dDec [mas]')
        plt.show()
        '''


