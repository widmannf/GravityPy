import matplotlib.pyplot as plt
import numpy as np
import logging
import os
from matplotlib import gridspec
from astropy.io import fits
from scipy import interpolate, optimize

from .utils import *

try:
    from generalFunctions import *
    set_style('show')
except (ValueError, NameError, ModuleNotFoundError):
    pass


def get_met(Volts, fc=False, removefc=True, returncomplex=False):
    V = np.array([np.convolve(Volts[:, i], np.ones(100)/100, 'same')
                  for i in range(80)]).T
    VC = V[:, 1::2] + 1j * V[:, ::2]

    if fc:
        VFCFT, VFCST = VC[:, 32:36], VC[:, 36:]
        VFCFT = (VFCFT) / abs(VFCFT)
        VFCST = (VFCST) / abs(VFCST)
        phaseFT = np.angle(VFCFT * np.conj(VFCFT.mean(axis=0)))
        phaseSC = np.angle(VFCST * np.conj(VFCST.mean(axis=0)))
        return phaseFT, phaseSC

    VCT = np.zeros((len(VC), 32), dtype=complex)
    if removefc:
        for i in range(8):
            VCT[:, 4*i:4*(i+1)] = (
                VC[:, 4*i:4*(i+1)] * np.conj(VC[:, 32 + i])[:, None]
            )
    else:
        VCT = VC[:, :-8]

    # Second np.convolve with time to gain in SNR (400DIT=800ms)
    VTEL = np.array([np.convolve(VCT[:, i], np.ones(150)/150, "same")
                     for i in range(32)]).T
    # VTELFC = (VTEL[:, :16] * np.conj(VTEL[:, 16:])).reshape(-1, 4, 4)
    VTELFT = VTEL[:, :16].reshape(-1, 4, 4)
    VTELST = VTEL[:, 16:].reshape(-1, 4, 4)

    for i in range(4):
        for j in range(4):
            VTELFT[:, i, j] = np.convolve(VTELFT[:, i, j],
                                          np.ones(100)/100, 'same')
            VTELST[:, i, j] = np.convolve(VTELST[:, i, j],
                                          np.ones(100)/100, 'same')
    # VTELFT = (VTELFT) / abs(VTELFT)
    # VTELST = (VTELST) / abs(VTELST)
    if returncomplex:
        return ((VTELFT * np.conj(VTELFT.mean(axis=0))),
                (VTELST * np.conj(VTELST.mean(axis=0))))

    phaseFT = np.unwrap(np.angle(VTELFT * np.conj(VTELFT.mean(axis=0))),
                        axis=0)
    phaseSC = np.unwrap(np.angle(VTELST * np.conj(VTELST.mean(axis=0))),
                        axis=0)
    rmsFT = np.std(phaseFT, axis=0)
    rmsSC = np.std(phaseSC, axis=0)
    phaseFT = np.angle(VTELFT * np.conj(VTELFT.mean(axis=0)))
    phaseSC = np.angle(VTELST * np.conj(VTELST.mean(axis=0)))
    return phaseFT, phaseSC, rmsFT, rmsSC


def get_refangle(header, tel, length):
    pa1 = header["ESO ISS PARANG START"]
    pa2 = header["ESO ISS PARANG END"]
    if (pa1-pa2) > 300:
        pa1 -= 360
    elif (pa1-pa2) < -300:
        pa1 += 360
    parang = np.linspace(pa1, pa2, length+1)
    parang = parang[:-1]
    drottoff = header["ESO INS DROTOFF" + str(4-tel)]
    try:
        dx = header["ESO INS SOBJ X"] - header["ESO INS SOBJ OFFX"]
        dy = header["ESO INS SOBJ Y"] - header["ESO INS SOBJ OFFY"]
    except KeyError:
        dx = header["ESO INS SOBJ X"]
        dy = header["ESO INS SOBJ Y"]
    posangle = np.arctan2(dx, dy) * 180 / np.pi
    fangle = - posangle - drottoff + 270
    angle = fangle + parang + 45.
    return (angle) % 360

def averaging(x, N, median=False):
    if N == 1:
        return x
    if x.ndim == 2:
        res = np.zeros((x.shape[0], x.shape[1]//N))
        for idx in range(x.shape[0]):
            if median:
                res[idx] = np.nanmedian(x[idx].reshape(-1, N), axis=1)
            else:
                res[idx] = np.nanmean(x[idx].reshape(-1, N), axis=1)
        return res
    elif x.ndim == 1:
        ll = x.shape[0]
        xx = np.pad(x, (0, N - ll % N), constant_values=np.nan)
        if median:
            res = np.nanmedian(xx.reshape(-1, N), axis=1)
        else:
            res = np.nanmean(xx.reshape(-1, N), axis=1)
        return res


def averaging_std(x, N):
    if x.ndim == 2:
        res = np.zeros((x.shape[0], x.shape[1]//N))
        for idx in range(x.shape[0]):
            res[idx] = np.nanstd(x[idx].reshape(-1, N), axis=1)
        return res
    elif x.ndim == 1:
        ll = x.shape[0]
        xx = np.pad(x, (0, N - ll % N), constant_values=np.nan)
        res = np.nanstd(xx.reshape(-1, N), axis=1)
        return res


def get_angle_header_all(header, tel, length):
    pa1 = header["ESO ISS PARANG START"]
    pa2 = header["ESO ISS PARANG END"]
    parang = np.linspace(pa1, pa2, length+1)
    parang = parang[:-1]
    drottoff = header["ESO INS DROTOFF" + str(4-tel)]
    dx = header["ESO INS SOBJ X"] - header["ESO INS SOBJ OFFX"]
    dy = header["ESO INS SOBJ Y"] - header["ESO INS SOBJ OFFY"]
    posangle = np.arctan2(dx, dy) * 180 / np.pi;
    fangle = - posangle - drottoff + 270
    angle = fangle + parang + 45.
    return angle % 360


def get_angle_header_start(header, tel):
    pa1 = header["ESO ISS PARANG START"]
    parang = pa1
    drottoff = header["ESO INS DROTOFF" + str(4-tel)]
    dx = header["ESO INS SOBJ X"] - header["ESO INS SOBJ OFFX"]
    dy = header["ESO INS SOBJ Y"] - header["ESO INS SOBJ OFFY"]
    posangle = np.arctan2(dx, dy) * 180 / np.pi;
    fangle = - posangle - drottoff + 270
    angle = fangle + parang + 45.
    return angle % 360


def get_angle_header_mean(header, tel):
    pa1 = header["ESO ISS PARANG START"]
    pa2 = header["ESO ISS PARANG END"]
    parang = (pa1+pa2)/2
    drottoff = header["ESO INS DROTOFF" + str(4-tel)]
    dx = header["ESO INS SOBJ X"] - header["ESO INS SOBJ OFFX"]
    dy = header["ESO INS SOBJ Y"] - header["ESO INS SOBJ OFFY"]
    posangle = np.arctan2(dx, dy) * 180 / np.pi;
    fangle = - posangle - drottoff + 270
    angle = fangle + parang + 45.
    return angle % 360


def rotation(ang):
    return np.array([[np.cos(ang), np.sin(ang)],
                     [-np.sin(ang), np.cos(ang)]])


class GravData():
    def __init__(self, data, loglevel='INFO', plot=False,
                 datacatg=None, test=False):
        """
        GravData: Class to load GRAVITY datafiles

        Main functions:
        get_int_data : load all interverometric data into class atributes
        get_flux_from_RAW : get the flux from the raw detector t_files
        get_dlambda : loads wavelength and spectral channels
        av_phases : properly average phases in phasor space
        calibrate_phi : Calibrate visibility phases
        """
        log_level = log_level_mapping.get(loglevel, logging.INFO)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        self.name = data
        self.test = test
        self.filename = os.path.basename(data)
        self.colors_baseline = np.array(['k', 'darkblue', color4,
                                         color2, 'darkred', color1])
        self.colors_closure = np.array([color1, 'darkred', 'k', color2])

        poscatg = ['VIS_DUAL_SCI_RAW', 'VIS_SINGLE_SCI_RAW',
                   'VIS_SINGLE_CAL_RAW', 'VIS_DUAL_CAL_RAW',
                   'VIS_SINGLE_CALIBRATED', 'VIS_DUAL_CALIBRATED',
                   'SINGLE_SCI_VIS', 'SINGLE_SCI_VIS_CALIBRATED',
                   'DUAL_SCI_VIS', 'DUAL_SCI_VIS_CALIBRATED',
                   'SINGLE_CAL_VIS', 'DUAL_CAL_VIS', 'ASTROREDUCED',
                   'DUAL_SCI_P2VMRED']

        header = fits.open(self.name)[0].header
        date_obs = header['DATE-OBS']

        self.header = header
        self.date_obs = date_obs
        self.date = convert_date(date_obs)
        self.raw = False

        if 'GRAV' not in header['INSTRUME']:
            raise ValueError('File seems to be not from GRAVITY')
        if datacatg is None:
            if 'ESO PRO CATG' in header:
                datacatg = header['ESO PRO CATG']
                if datacatg not in poscatg:
                    raise ValueError('filetype is %s, which is not supported'
                                     % datacatg)
            else:
                self.logger.info('Assume this is a raw file!')
                datacatg = 'RAW'
        if datacatg == 'RAW':
            self.raw = True

        self.datacatg = datacatg
        self.polmode = header['ESO INS POLA MODE']
        self.resolution = header['ESO INS SPEC RES']
        self.dit = header['ESO DET2 SEQ1 DIT']
        self.ndit = header['ESO DET2 NDIT']
        self.mjd = convert_date(header['DATE-OBS'], mjd=True)

        if 'P2VM' in self.datacatg:
            self.p2vm_file = True
        else:
            self.p2vm_file = False

        tel = fits.open(self.name)[0].header["TELESCOP"]
        if tel in ['ESO-VLTI-U1234', 'U1234']:
            self.tel = 'UT'
        elif tel in ['ESO-VLTI-A1234', 'A1234']:
            self.tel = 'AT'
        else:
            self.tel = 'test'
            if not self.test:
                raise ValueError('Telescope not AT or UT, seomtehign '
                                 'wrong with input data')

        # Get BL names
        if self.raw or self.p2vm_file:
            self.baseline_labels = np.array(["UT4-3", "UT4-2", "UT4-1",
                                            "UT3-2", "UT3-1", "UT2-1"])
            self.closure_labels = np.array(["UT4-3-2", "UT4-3-1",
                                            "UT4-2-1", "UT3-2-1"])
        else:
            baseline_labels = []
            closure_labels = []
            tel_name = fits.open(self.name)['OI_ARRAY'].data['TEL_NAME']
            sta_index = fits.open(self.name)['OI_ARRAY'].data['STA_INDEX']
            if self.polmode == 'SPLIT':
                vis_index = fits.open(self.name)['OI_VIS', 11].data['STA_INDEX']
                t3_index = fits.open(self.name)['OI_T3', 11].data['STA_INDEX']
            else:
                vis_index = fits.open(self.name)['OI_VIS', 10].data['STA_INDEX']
                t3_index = fits.open(self.name)['OI_T3', 10].data['STA_INDEX']
            for bl in range(6):
                t1 = np.where(sta_index == vis_index[bl, 0])[0][0]
                t2 = np.where(sta_index == vis_index[bl, 1])[0][0]
                baseline_labels.append(tel_name[t1] + '-' + tel_name[t2][2])
            for cl in range(4):
                t1 = np.where(sta_index == t3_index[cl, 0])[0][0]
                t2 = np.where(sta_index == t3_index[cl, 1])[0][0]
                t3 = np.where(sta_index == t3_index[cl, 2])[0][0]
                closure_labels.append(tel_name[t1] + '-'
                                      + tel_name[t2][2] + '-' + tel_name[t3][2])
            self.closure_labels = np.array(closure_labels)
            self.baseline_labels = np.array(baseline_labels)

        self.logger.debug(f'Category: {self.datacatg}')
        self.logger.debug(f'Telescope: {self.tel}')
        self.logger.debug(f'Polarization: {self.polmode}')
        self.logger.debug(f'Resolution: {self.resolution}')
        self.logger.debug(f'DIT: {self.dit}')
        self.logger.debug(f'NDIT: {self.ndit}')

        if not self.raw:
            if self.polmode == 'SPLIT':
                self.wlSC_P1 = fits.open(self.name)['OI_WAVELENGTH', 11].data['EFF_WAVE']*1e6
                self.wlSC_P2 = fits.open(self.name)['OI_WAVELENGTH', 12].data['EFF_WAVE']*1e6
                self.wlSC = self.wlSC_P1
                self.channel = len(self.wlSC_P1)
                if not datacatg == 'ASTROREDUCED':
                    self.wlFT_P1 = fits.open(self.name)['OI_WAVELENGTH', 21].data['EFF_WAVE']*1e6
                    self.wlFT_P2 = fits.open(self.name)['OI_WAVELENGTH', 22].data['EFF_WAVE']*1e6

            elif self.polmode == 'COMBINED':
                self.wlSC = fits.open(self.name)['OI_WAVELENGTH', 10].data['EFF_WAVE']*1e6
                self.channel = len(self.wlSC)
                if not datacatg == 'ASTROREDUCED':
                    self.wlFT = fits.open(self.name)['OI_WAVELENGTH', 20].data['EFF_WAVE']*1e6

    def get_flux(self, mode='SC', plot=False):
        """
        Get the flux data
        """
        if self.raw:
            raise ValueError('Input is a RAW file, not usable for this function')
        if self.polmode == 'SPLIT':
            self.fluxtime = fits.open(self.name)['OI_FLUX', 11].data['MJD']
            if mode =='SC':
                self.fluxSC_P1 = fits.open(self.name)['OI_FLUX', 11].data['FLUX']
                self.fluxSC_P2 = fits.open(self.name)['OI_FLUX', 12].data['FLUX']
                self.fluxerrSC_P1 = fits.open(self.name)['OI_FLUX', 11].data['FLUXERR']
                self.fluxerrSC_P2 = fits.open(self.name)['OI_FLUX', 12].data['FLUXERR']
                if plot:
                    if np.ndim(self.fluxSC_P1) > 1:
                        for idx in range(len(self.fluxSC_P1)):
                            plt.errorbar(self.wlSC_P1, self.fluxSC_P1[idx], self.fluxerrSC_P1[idx], color=color1)
                            plt.errorbar(self.wlSC_P2, self.fluxSC_P2[idx], self.fluxerrSC_P2[idx], color='k')
                    else:
                        plt.errorbar(self.wlSC_P1, self.fluxSC_P1, self.fluxerrSC_P1, color=color1)
                        plt.errorbar(self.wlSC_P2, self.fluxSC_P2, self.fluxerrSC_P2, color='k')
                    plt.show()
                return self.fluxtime, self.fluxSC_P1, self.fluxerrSC_P1, self.fluxSC_P2, self.fluxerrSC_P2

            elif mode =='FT':
                if self.datacatg == 'ASTROREDUCED':
                    raise ValueError('Astroreduced has no FT values')
                self.fluxFT_P1 = fits.open(self.name)['OI_FLUX', 21].data['FLUX']
                self.fluxFT_P2 = fits.open(self.name)['OI_FLUX', 22].data['FLUX']
                self.fluxerrFT_P1 = fits.open(self.name)['OI_FLUX', 21].data['FLUXERR']
                self.fluxerrFT_P2 = fits.open(self.name)['OI_FLUX', 22].data['FLUXERR']
                if plot:
                    if np.ndim(self.fluxFT_P1) > 1:
                        for idx in range(len(self.fluxFT_P1)):
                            plt.errorbar(self.wlFT_P1, self.fluxFT_P1[idx], self.fluxerrFT_P1[idx], color=color1)
                            plt.errorbar(self.wlFT_P2, self.fluxFT_P2[idx], self.fluxerrFT_P2[idx], color='k')
                    else:
                        plt.errorbar(self.wlFT_P1, self.fluxFT_P1, self.fluxerrFT_P1, color=color1)
                        plt.errorbar(self.wlFT_P2, self.fluxFT_P2, self.fluxerrFT_P2, color='k')
                    plt.show()
                return self.fluxtime, self.fluxFT_P1, self.fluxerrFT_P1, self.fluxFT_P2, self.fluxerrFT_P2

            else:
                raise ValueError('Mode has to be SC or FT')

        elif self.polmode == 'COMBINED':
            self.fluxtime = fits.open(self.name)['OI_FLUX', 10].data['MJD']
            if mode =='SC':
                self.fluxSC = fits.open(self.name)['OI_FLUX', 10].data['FLUX']
                self.fluxerrSC = fits.open(self.name)['OI_FLUX', 10].data['FLUXERR']
                if plot:
                    if np.ndim(self.fluxSC) > 1:
                        for idx in range(len(self.fluxSC)):
                            plt.errorbar(self.wlSC, self.fluxSC[idx], self.fluxerrSC[idx])
                    else:
                        plt.errorbar(self.wlSC, self.fluxSC, self.fluxerrSC, color=color1)
                    plt.xlabel('Wavelength [$\mu$m]')
                    plt.ylabel('Flux')
                    plt.show()
                return self.fluxtime, self.fluxSC, self.fluxerrSC

            elif mode =='FT':
                if self.datacatg == 'ASTROREDUCED':
                    raise ValueError('Astroreduced has no FT values')
                self.fluxFT = fits.open(self.name)['OI_FLUX', 20].data['FLUX']
                self.fluxerrFT = fits.open(self.name)['OI_FLUX', 20].data['FLUXERR']
                if plot:
                    if np.ndim(self.fluxFT) > 1:
                        for idx in range(len(self.fluxFT)):
                            plt.errorbar(self.wlFT, self.fluxFT[idx], self.fluxerrFT[idx])
                    else:
                        plt.errorbar(self.wlFT, self.fluxFT, self.fluxerrFT, color=color1)
                    plt.show()
                return self.fluxtime, self.fluxFT, self.fluxerrFT

    def get_int_data(self, mode='SC', plot=False, plotTAmp=False, flag=False,
                   reload=False, ignore_tel=[]):
        """
        Reads out all interferometric data and saves it into the class:
        visamp, visphi, visphi2, closure amplitude and phase
        if plot it plots all data

        """
        if self.raw:
            raise ValueError('Input is a RAW file,',
                             'not usable for this function')
        if self.p2vm_file:
            raise ValueError('Input is a p2vmred file,',
                             'not usable for this function')

        fitsdata = fits.open(self.name)
        if self.polmode == 'SPLIT':
            if mode =='SC':
                self.u = fitsdata['OI_VIS', 11].data.field('UCOORD')
                self.v = fitsdata['OI_VIS', 11].data.field('VCOORD')

                wave = self.wlSC_P1
                self.wave = wave
                u_as = np.zeros((len(self.u), len(wave)))
                v_as = np.zeros((len(self.v), len(wave)))
                for i in range(0, len(self.u)):
                    u_as[i, :] = (self.u[i] / (wave * 1.e-6)
                                  * np.pi / 180. / 3600.)  # 1/as
                    v_as[i, :] = (self.v[i] / (wave * 1.e-6)
                                  * np.pi / 180. / 3600.)  # 1/as
                self.spFrequAS = np.sqrt(u_as**2.+v_as**2.)

                magu = np.sqrt(self.u**2.+self.v**2.)
                max_spf = np.zeros((len(magu)//6*4))
                for idx in range(len(magu)//6):
                    max_spf[0 + idx*4] = np.max(np.array([magu[0 + idx*6],
                                                          magu[3 + idx*6],
                                                          magu[1 + idx*6]]))
                    max_spf[1 + idx*4] = np.max(np.array([magu[0 + idx*6],
                                                          magu[4 + idx*6],
                                                          magu[2 + idx*6]]))
                    max_spf[2 + idx*4] = np.max(np.array([magu[1 + idx*6],
                                                          magu[5 + idx*6],
                                                          magu[2 + idx*6]]))
                    max_spf[3 + idx*4] = np.max(np.array([magu[3 + idx*6],
                                                          magu[5 + idx*6],
                                                          magu[4 + idx*6]]))

                self.max_spf = max_spf
                spFrequAS_T3 = np.zeros((len(max_spf), len(wave)))
                for idx in range(len(max_spf)):
                    spFrequAS_T3[idx] = (max_spf[idx]/(wave*1.e-6)
                                         * np.pi / 180. / 3600.)  # 1/as
                self.spFrequAS_T3 = spFrequAS_T3
                self.bispec_ind = np.array([[0, 3, 1],
                                            [0, 4, 2],
                                            [1, 5, 2],
                                            [3, 5, 4]])
                
                if not hasattr(self, 'visphiSC_P1') or reload:
                    # Data
                    # P1
                    self.visampSC_P1 = fitsdata['OI_VIS', 11].data.field('VISAMP')
                    self.visamperrSC_P1 = fitsdata['OI_VIS', 11].data.field('VISAMPERR')
                    self.visphiSC_P1 = fitsdata['OI_VIS', 11].data.field('VISPHI')
                    self.visphierrSC_P1 = fitsdata['OI_VIS', 11].data.field('VISPHIERR')
                    self.vis2SC_P1 = fitsdata['OI_VIS2', 11].data.field('VIS2DATA')
                    self.vis2errSC_P1 = fitsdata['OI_VIS2', 11].data.field('VIS2ERR')
                    self.t3SC_P1 = fitsdata['OI_T3', 11].data.field('T3PHI')
                    self.t3errSC_P1 = fitsdata['OI_T3', 11].data.field('T3PHIERR')
                    self.t3ampSC_P1 = fitsdata['OI_T3', 11].data.field('T3AMP')
                    self.t3amperrSC_P1 = fitsdata['OI_T3', 11].data.field('T3AMPERR')
                    # P2
                    self.visampSC_P2 = fitsdata['OI_VIS', 12].data.field('VISAMP')
                    self.visamperrSC_P2 = fitsdata['OI_VIS', 12].data.field('VISAMPERR')
                    self.visphiSC_P2 = fitsdata['OI_VIS', 12].data.field('VISPHI')
                    self.visphierrSC_P2 = fitsdata['OI_VIS', 12].data.field('VISPHIERR')
                    self.vis2SC_P2 = fitsdata['OI_VIS2', 12].data.field('VIS2DATA')
                    self.vis2errSC_P2 = fitsdata['OI_VIS2', 12].data.field('VIS2ERR')
                    self.t3SC_P2 = fitsdata['OI_T3', 12].data.field('T3PHI')
                    self.t3errSC_P2 = fitsdata['OI_T3', 12].data.field('T3PHIERR')
                    self.t3ampSC_P2 = fitsdata['OI_T3', 12].data.field('T3AMP')
                    self.t3amperrSC_P2 = fitsdata['OI_T3', 12].data.field('T3AMPERR')

                    # Flags
                    self.visampflagSC_P1 = fitsdata['OI_VIS', 11].data.field('FLAG')
                    self.visampflagSC_P2 = fitsdata['OI_VIS', 12].data.field('FLAG')
                    self.vis2flagSC_P1 = fitsdata['OI_VIS2', 11].data.field('FLAG')
                    self.vis2flagSC_P2 = fitsdata['OI_VIS2', 12].data.field('FLAG')
                    self.t3flagSC_P1 = fitsdata['OI_T3', 11].data.field('FLAG')
                    self.t3flagSC_P2 = fitsdata['OI_T3', 12].data.field('FLAG')
                    self.t3ampflagSC_P1 = fitsdata['OI_T3', 11].data.field('FLAG')
                    self.t3ampflagSC_P2 = fitsdata['OI_T3', 12].data.field('FLAG')
                    self.visphiflagSC_P1 = fitsdata['OI_VIS', 11].data.field('FLAG')
                    self.visphiflagSC_P2 = fitsdata['OI_VIS', 12].data.field('FLAG')

                for t in ignore_tel:
                    for cdx, cl in enumerate(self.closure_labels):
                        if str(t) in cl:
                            self.t3flagSC_P1[cdx] = True
                            self.t3flagSC_P2[cdx] = True
                            self.t3ampflagSC_P1[cdx] = True
                            self.t3ampflagSC_P2[cdx] = True
                    for vdx, vi in enumerate(self.baseline_labels):
                        if str(t) in vi:
                            self.visampflagSC_P1[vdx] = True
                            self.visampflagSC_P2[vdx] = True
                            self.vis2flagSC_P1[vdx] = True
                            self.vis2flagSC_P2[vdx] = True
                            self.visphiflagSC_P1[vdx] = True
                            self.visphiflagSC_P2[vdx] = True

                if flag:
                    self.visampSC_P1[self.visampflagSC_P1] = np.nan
                    self.visamperrSC_P1[self.visampflagSC_P1] = np.nan
                    self.visampSC_P2[self.visampflagSC_P2] = np.nan
                    self.visamperrSC_P2[self.visampflagSC_P2] = np.nan

                    self.vis2SC_P1[self.vis2flagSC_P1] = np.nan
                    self.vis2errSC_P1[self.vis2flagSC_P1] = np.nan
                    self.vis2SC_P2[self.vis2flagSC_P2] = np.nan
                    self.vis2errSC_P2[self.vis2flagSC_P2] = np.nan

                    self.t3SC_P1[self.t3flagSC_P1] = np.nan
                    self.t3errSC_P1[self.t3flagSC_P1] = np.nan
                    self.t3SC_P2[self.t3flagSC_P2] = np.nan
                    self.t3errSC_P2[self.t3flagSC_P2] = np.nan

                    self.t3ampSC_P1[self.t3ampflagSC_P1] = np.nan
                    self.t3amperrSC_P1[self.t3ampflagSC_P1] = np.nan
                    self.t3ampSC_P2[self.t3ampflagSC_P2] = np.nan
                    self.t3amperrSC_P2[self.t3ampflagSC_P2] = np.nan

                    self.visphiSC_P1[self.visphiflagSC_P1] = np.nan
                    self.visphierrSC_P1[self.visphiflagSC_P1] = np.nan
                    self.visphiSC_P2[self.visphiflagSC_P2] = np.nan
                    self.visphierrSC_P2[self.visphiflagSC_P2] = np.nan

                self.int_data = [[self.visampSC_P1, self.visampSC_P2,
                                  self.vis2SC_P1, self.vis2SC_P2,
                                  self.t3SC_P1, self.t3SC_P2,
                                  self.visphiSC_P1, self.visphiSC_P2],
                                 [self.visamperrSC_P1, self.visamperrSC_P2,
                                  self.vis2errSC_P1, self.vis2errSC_P2,
                                  self.t3errSC_P1, self.t3errSC_P2,
                                  self.visphierrSC_P1, self.visphierrSC_P2],
                                 [self.visampflagSC_P1, self.visampflagSC_P2,
                                  self.vis2flagSC_P1, self.vis2flagSC_P2,
                                  self.t3flagSC_P1, self.t3flagSC_P2,
                                  self.visphiflagSC_P1, self.visphiflagSC_P2]]

                if plot:
                    if plotTAmp:
                        gs = gridspec.GridSpec(3, 2)
                        plt.figure(figsize=(15, 15))
                    else:
                        gs = gridspec.GridSpec(2, 2)
                        plt.figure(figsize=(15, 12))

                    axis = plt.subplot(gs[0, 0])
                    for idx in range(len(self.vis2SC_P1)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.visampSC_P1[idx],
                                     self.visamperrSC_P1[idx],
                                     alpha=0.7, ms=4, lw=0.5, capsize=0,
                                     ls='', marker='o',
                                     color=self.colors_baseline[idx % 6])
                    for idx in range(len(self.vis2SC_P2)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.visampSC_P2[idx],
                                     self.visamperrSC_P2[idx],
                                     alpha=0.7, ms=4, lw=0.5, capsize=0,
                                     ls='', marker='D',
                                     color=self.colors_baseline[idx % 6])
                    plt.axhline(1, ls='--', lw=0.5)
                    plt.ylim(-0.0, 1.1)
                    plt.ylabel('visibility amplitude')

                    axis = plt.subplot(gs[0, 1])
                    for idx in range(len(self.vis2SC_P1)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.vis2SC_P1[idx],
                                     self.vis2errSC_P1[idx],
                                     alpha=0.7, ms=4, lw=0.5, capsize=0,
                                     ls='', marker='o',
                                     color=self.colors_baseline[idx % 6],
                                     label=self.baseline_labels[idx % 6])
                        if idx == 5:
                            plt.legend(frameon=True)
                    for idx in range(len(self.vis2SC_P2)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.vis2SC_P2[idx],
                                     self.vis2errSC_P2[idx],
                                     alpha=0.7, ms=4, lw=0.5, capsize=0,
                                     ls='', marker='D',
                                     color=self.colors_baseline[idx % 6])
                    plt.axhline(1, ls='--', lw=0.5)
                    plt.ylim(-0.0, 1.1)
                    plt.ylabel('visibility squared')

                    axis = plt.subplot(gs[1, 0])
                    for idx in range(len(self.t3SC_P2)):
                        plt.errorbar(self.spFrequAS_T3[idx],
                                     self.t3SC_P2[idx],
                                     self.t3errSC_P2[idx],
                                     alpha=0.7, ms=4, lw=0.5,
                                     capsize=0, marker='o', ls='',
                                     color=self.colors_closure[idx % 4],
                                     label=self.closure_labels[idx % 4])
                        if idx == 3:
                            plt.legend(frameon=True)
                    for idx in range(len(self.t3SC_P2)):
                        plt.errorbar(self.spFrequAS_T3[idx],
                                     self.t3SC_P1[idx],
                                     self.t3errSC_P1[idx],
                                     alpha=0.7, ms=4, lw=0.5, capsize=0,
                                     marker='D', ls='',
                                     color=self.colors_closure[idx % 4])
                    plt.axhline(0, ls='--', lw=0.5)
                    plt.xlabel('spatial frequency (1/arcsec)')
                    plt.ylabel('closure phase (deg)')

                    axis = plt.subplot(gs[1, 1])
                    if plotTAmp:
                        for idx in range(len(self.t3SC_P2)):
                            plt.errorbar(self.spFrequAS_T3[idx],
                                         self.t3ampSC_P2[idx],
                                         self.t3amperrSC_P2[idx],
                                         marker='o', ls='',
                                         color=self.colors_closure[idx % 4])
                        for idx in range(len(self.t3SC_P2)):
                            plt.errorbar(self.spFrequAS_T3[idx],
                                         self.t3ampSC_P1[idx],
                                         self.t3amperrSC_P1[idx],
                                         marker='p', ls='',
                                         color=self.colors_closure[idx % 4])
                        plt.axhline(1, ls='--', lw=0.5)
                        plt.ylim(-0.0, 1.1)
                        plt.xlabel('spatial frequency (1/arcsec)')
                        plt.ylabel('closure amplitude')

                        axis = plt.subplot(gs[2, 1])

                    for idx in range(len(self.vis2SC_P1)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.visphiSC_P1[idx],
                                     self.visphierrSC_P1[idx],
                                     alpha=0.7, ms=4, lw=0.5, capsize=0,
                                     ls='', marker='o',
                                     color=self.colors_baseline[idx % 6])
                    for idx in range(len(self.vis2SC_P2)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.visphiSC_P2[idx],
                                     self.visphierrSC_P2[idx],
                                     alpha=0.7, ms=4, lw=0.5, capsize=0,
                                     ls='', marker='p',
                                     color=self.colors_baseline[idx % 6])
                    plt.axhline(0, ls='--', lw=0.5)
                    plt.xlabel('spatial frequency (1/arcsec)')
                    plt.ylabel('visibility phase')
                    plt.show()

        if self.polmode == 'COMBINED':
            if mode == 'SC':
                self.u = fitsdata['OI_VIS', 10].data.field('UCOORD')
                self.v = fitsdata['OI_VIS', 10].data.field('VCOORD')

                # spatial frequency
                wave = self.wlSC
                self.wave = wave
                u_as = np.zeros((len(self.u), len(wave)))
                v_as = np.zeros((len(self.v), len(wave)))
                for i in range(0, len(self.u)):
                    u_as[i, :] = (self.u[i]/(wave*1.e-6)
                                  * np.pi / 180. / 3600.)  # 1/as
                    v_as[i, :] = (self.v[i]/(wave*1.e-6)
                                  * np.pi / 180. / 3600.)  # 1/as
                self.spFrequAS = np.sqrt(u_as**2.+v_as**2.)

                # spatial frequency T3
                magu = np.sqrt(self.u**2. + self.v**2.)
                max_spf = np.zeros(int(len(magu)/6*4))
                for idx in range(len(magu)//6):
                    max_spf[0 + idx*4] = np.max(np.array([magu[0 + idx*6],
                                                          magu[3 + idx*6],
                                                          magu[1 + idx*6]]))
                    max_spf[1 + idx*4] = np.max(np.array([magu[0 + idx*6],
                                                          magu[4 + idx*6],
                                                          magu[2 + idx*6]]))
                    max_spf[2 + idx*4] = np.max(np.array([magu[1 + idx*6],
                                                          magu[5 + idx*6],
                                                          magu[2 + idx*6]]))
                    max_spf[3 + idx*4] = np.max(np.array([magu[3 + idx*6],
                                                          magu[5 + idx*6],
                                                          magu[4 + idx*6]]))
                self.max_spf = max_spf
                spFrequAS_T3 = np.zeros((len(max_spf), len(wave)))
                for idx in range(len(max_spf)):
                    spFrequAS_T3[idx] = (max_spf[idx]/(wave*1.e-6)
                                         * np.pi / 180. / 3600.)  # 1/as
                self.spFrequAS_T3 = spFrequAS_T3
                self.bispec_ind = np.array([[0, 3, 1],
                                            [0, 4, 2],
                                            [1, 5, 2],
                                            [3, 5, 4]])

                # Data
                # P1
                self.visampSC = fitsdata['OI_VIS', 10].data.field('VISAMP')
                self.visamperrSC = fitsdata['OI_VIS', 10].data.field('VISAMPERR')
                self.visphiSC = fitsdata['OI_VIS', 10].data.field('VISPHI')
                self.visphierrSC = fitsdata['OI_VIS', 10].data.field('VISPHIERR')
                self.vis2SC = fitsdata['OI_VIS2', 10].data.field('VIS2DATA')
                self.vis2errSC = fitsdata['OI_VIS2', 10].data.field('VIS2ERR')
                self.t3SC = fitsdata['OI_T3', 10].data.field('T3PHI')
                self.t3errSC = fitsdata['OI_T3', 10].data.field('T3PHIERR')
                self.t3ampSC = fitsdata['OI_T3', 10].data.field('T3AMP')
                self.t3amperrSC = fitsdata['OI_T3', 10].data.field('T3AMPERR')

                # Flags
                self.visampflagSC = fitsdata['OI_VIS', 10].data.field('FLAG')
                self.vis2flagSC = fitsdata['OI_VIS2', 10].data.field('FLAG')
                self.t3flagSC = fitsdata['OI_T3', 10].data.field('FLAG')
                self.t3ampflagSC = fitsdata['OI_T3', 10].data.field('FLAG')
                self.visphiflagSC = fitsdata['OI_VIS', 10].data.field('FLAG')

                for t in ignore_tel:
                    for cdx, cl in enumerate(self.closure_labels):
                        if str(t) in cl:
                            self.t3flagSC[cdx] = True
                            self.t3ampflagSC[cdx] = True
                    for vdx, vi in enumerate(self.baseline_labels):
                        if str(t) in vi:
                            self.visampflagSC[vdx] = True
                            self.vis2flagSC[vdx] = True
                            self.visphiflagSC[vdx] = True

                if flag:
                    self.visampSC[self.visampflagSC] = np.nan
                    self.visamperrSC[self.visampflagSC] = np.nan
                    self.vis2SC[self.vis2flagSC] = np.nan
                    self.vis2errSC[self.vis2flagSC] = np.nan
                    self.t3SC[self.t3flagSC] = np.nan
                    self.t3errSC[self.t3flagSC] = np.nan
                    self.t3ampSC[self.t3ampflagSC] = np.nan
                    self.t3amperrSC[self.t3ampflagSC] = np.nan
                    self.visphiSC[self.visphiflagSC] = np.nan
                    self.visphierrSC[self.visphiflagSC] = np.nan

                if plot:
                    if plotTAmp:
                        gs = gridspec.GridSpec(3, 2)
                        plt.figure(figsize=(15, 15))
                    else:
                        gs = gridspec.GridSpec(2, 2)
                        plt.figure(figsize=(15, 12))
                    axis = plt.subplot(gs[0, 0])
                    for idx in range(len(self.vis2SC)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.visampSC[idx],
                                     self.visamperrSC[idx],
                                     ls='', marker='o',
                                     color=self.colors_baseline[idx % 6])
                    plt.axhline(1, ls='--', lw=0.5)
                    plt.ylim(-0.0, 1.1)
                    plt.ylabel('visibility amplitude')

                    axis = plt.subplot(gs[0, 1])
                    for idx in range(len(self.vis2SC)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.vis2SC[idx],
                                     self.vis2errSC[idx],
                                     ls='', marker='o',
                                     color=self.colors_baseline[idx % 6])
                    plt.axhline(1, ls='--', lw=0.5)
                    plt.ylim(-0.0, 1.1)
                    plt.ylabel('visibility squared')

                    axis = plt.subplot(gs[1, 0])
                    for idx in range(len(self.t3SC)):
                        plt.errorbar(self.spFrequAS_T3[idx],
                                     self.t3SC[idx],
                                     self.t3errSC[idx],
                                     marker='o', ls='',
                                     color=self.colors_closure[idx % 4])
                    plt.axhline(0, ls='--', lw=0.5)
                    plt.xlabel('spatial frequency (1/arcsec)')
                    plt.ylabel('closure phase (deg)')

                    axis = plt.subplot(gs[1, 1])
                    if plotTAmp:
                        for idx in range(len(self.t3SC)):
                            plt.errorbar(self.spFrequAS_T3[idx],
                                         self.t3ampSC[idx],
                                         self.t3amperrSC[idx],
                                         marker='o', ls='',
                                         color=self.colors_closure[idx % 4])
                        plt.axhline(1, ls='--', lw=0.5)
                        plt.ylim(-0.0, 1.1)
                        plt.xlabel('spatial frequency (1/arcsec)')
                        plt.ylabel('closure amplitude')

                        axis = plt.subplot(gs[2, 1])
                    for idx in range(len(self.vis2SC)):
                        plt.errorbar(self.spFrequAS[idx],
                                     self.visphiSC[idx],
                                     self.visphierrSC[idx],
                                     ls='', marker='o',
                                     color=self.colors_baseline[idx % 6])
                    plt.axhline(0, ls='--', lw=0.5)
                    plt.xlabel('spatial frequency (1/arcsec)')
                    plt.ylabel('visibility phase')
                    plt.show()
        fitsdata.close()

    def get_flux_from_RAW(self, flatfile, method='preproc', skyfile=None,
                          wavefile=None, p2vmfile=None, flatflux=False,
                          darkfile=None):
        """
        Get the flux values from a raw file
        method has to be 'spectrum', 'preproc', 'p2vmred', 'dualscivis'
        Depending on the method the flux extraction from the raw detector
        frames is done until the given endproduct
        """
        if not self.raw:
            raise ValueError('File has to be a RAW file for this method')
        usableMethods = ['spectrum', 'preproc', 'p2vmred', 'dualscivis']
        if method not in usableMethods:
            raise TypeError('method not available, should be one of the following: %s' % usableMethods)

        raw = fits.open(self.name)['IMAGING_DATA_SC'].data
        if self.resolution != 'LOW':
            raw[raw > np.percentile(raw, 99.9)] = np.nan
        det_gain = 1.984

        if skyfile is None:
            self.logger.info('No skyfile given')
            red = raw*det_gain
        else:
            sky = fits.open(skyfile)['IMAGING_DATA_SC'].data
            red = (raw-sky)*det_gain

        if red.ndim == 3:
            tsteps = red.shape[0]

        # sum over spectra domain to find maxpos
        _speclist = np.sum(np.mean(red, 0), 1)
        _speclist[np.where(_speclist < 300)] = 0

        if self.polmode == 'SPLIT':
            numspec = 48
        elif self.polmode == 'COMBINED':
            numspec = 24

        flatfits = fits.open(flatfile)
        fieldstart = flatfits['PROFILE_PARAMS'].header['ESO PRO PROFILE STARTX'] - 1
        flatchannels = flatfits['PROFILE_PARAMS'].header['ESO PRO PROFILE NX']
        fieldstop = fieldstart + flatchannels

        if flatflux:
            flatdata = flatfits['IMAGING_DATA_SC'].data[0]
            flatdata += np.min(flatdata)
            flatdata /= np.max(flatdata)
            red[:, :, fieldstart:fieldstop] = red[:, :, fieldstart:fieldstop] / flatdata

        # extract spectra with profile
        red_spectra = np.zeros((tsteps, numspec, flatchannels))
        for idx in range(numspec):
            _specprofile = flatfits['PROFILE_DATA'].data['DATA%i' % (idx+1)]
            _specprofile_t = np.tile(_specprofile[0], (tsteps, 1, 1))
            red_spectra[:, idx] = np.nansum(red[:, :, fieldstart:fieldstop] * _specprofile_t, 1)

        if method == 'spectrum':
            return red_spectra
        elif wavefile is None:
            raise ValueError('wavefile needed!')
        elif p2vmfile is None:
            raise ValueError('pp_wl needed!')

        try:
            pp_wl = fits.open(p2vmfile)['OI_WAVELENGTH', 11].data['EFF_WAVE']
        except:
            pp_wl = fits.open(p2vmfile)['OI_WAVELENGTH', 10].data['EFF_WAVE']

        # wl interpolation
        wavefits = fits.open(wavefile)
        red_spectra_i = np.zeros((tsteps, numspec, len(pp_wl)))
        for tdx in range(tsteps):
            for idx in range(numspec):
                try:
                    red_spectra_i[tdx, idx,:] = interpolate.interp1d(wavefits['WAVE_DATA_SC'].data['DATA%i' % (idx+1)][0],
                                                                     red_spectra[tdx, idx])(pp_wl)
                except ValueError:
                    red_spectra_i[tdx, idx,:] = interpolate.interp1d(wavefits['WAVE_DATA_SC'].data['DATA%i' % (idx+1)][0],
                                                                     red_spectra[tdx, idx], bounds_error=False, fill_value='extrapolate')(pp_wl)
                    self.logger.warning('Extrapolation needed')

        if method == 'preproc':
            return pp_wl, red_spectra_i

        red_flux_P = np.zeros((tsteps, 4, len(pp_wl)))
        red_flux_S = np.zeros((tsteps, 4, len(pp_wl)))

        _red_spec_S = red_spectra_i[:, ::2, :]
        _red_spec_P = red_spectra_i[:, 1::2, :]
        _red_spec_SS = np.zeros((tsteps, 6, len(pp_wl)))
        _red_spec_PS = np.zeros((tsteps, 6, len(pp_wl)))
        for idx, i in enumerate(range(0, 24, 4)):
            _red_spec_SS[:, idx, :] = np.sum(_red_spec_S[:, i:i+4, :], 1)
            _red_spec_PS[:, idx, :] = np.sum(_red_spec_P[:, i:i+4, :], 1)

        T2BM = np.array([[0, 1, 0, 1],
                         [1, 0, 0, 1],
                         [1, 1, 0, 0],
                         [0, 0, 1, 1],
                         [0, 1, 1, 0],
                         [1, 0, 1, 0]])
        B2TM = np.linalg.pinv(T2BM)
        B2TM /= np.max(B2TM)

        for idx in range(tsteps):
            red_flux_P[idx] = np.dot(B2TM, _red_spec_PS[idx])
            red_flux_S[idx] = np.dot(B2TM, _red_spec_SS[idx])

        if method == 'p2vmred':
            return red_flux_P, red_flux_S

        if method == 'dualscivis':
            return np.sum(red_flux_P, 0), np.sum(red_flux_S, 0)

    def get_dlambda(self, idel=False):
        """
        Get the size of the spectral channels
        if idel it is taken from the hardcoded size of the response functions,
        otherwise it is read in from the OI_WAVELENGTH table
        TODO Idel + medium/high resolution needs some work
        """
        nwave = self.channel
        if self.polmode == 'COMBINED':
            effband = fits.open(self.name)['OI_WAVELENGTH', 10].data['EFF_BAND']
        elif self.polmode == 'SPLIT':
            effband = fits.open(self.name)['OI_WAVELENGTH', 11].data['EFF_BAND']
        dlambda = np.zeros((6, nwave))
        for idx in range(6):
            dlambda[idx] = effband/2*1e6
        self.dlambda = dlambda

    def av_phases(self, phases, axis=0):
        phases = np.exp(1j*np.radians(phases))
        phases = (np.nanmean(np.real(phases), axis=axis)
                  + 1j*np.nanmean(np.imag(phases), axis=axis))
        phases = np.angle(phases, deg=True)
        return phases

    def calibrate_phi(self, calibrator, plot=True):
        if not hasattr(self, 'visphiSC_P1'):
            self.get_int_data()
        c = fits.open(calibrator)
        c_channel = len(c['OI_WAVELENGTH', 11].data['EFF_WAVE'])
        if c_channel != self.channel:
            raise ValueError('Calibrator has different number '
                             'of spectral channels')
        cP1 = c['OI_VIS', 11].data['VISPHI']
        cP2 = c['OI_VIS', 12].data['VISPHI']
        cf1 = c['OI_VIS', 11].data['FLAG']
        cf2 = c['OI_VIS', 12].data['FLAG']
        cP1[cf1] = np.nan
        cP2[cf2] = np.nan
        cP1 = self.av_phases(cP1.reshape(-1, 6, self.channel))[np.newaxis, :, :]
        cP2 = self.av_phases(cP2.reshape(-1, 6, self.channel))[np.newaxis, :, :]

        sP1 = self.visphiSC_P1.reshape(-1, 6, self.channel)
        sP2 = self.visphiSC_P2.reshape(-1, 6, self.channel)

        self.visphiSC_P1 = np.angle(np.exp(1j*np.radians(sP1))
                                    / np.exp(1j*np.radians(cP1)), deg=True)
        self.visphiSC_P2 = np.angle(np.exp(1j*np.radians(sP2))
                                    / np.exp(1j*np.radians(cP2)), deg=True)

        if self.visphiSC_P1.shape[0] == 1:
            self.visphiSC_P1 = self.visphiSC_P1[0]
            self.visphiSC_P2 = self.visphiSC_P2[0]
        else:
            self.visphiSC_P1 = self.visphiSC_P1.reshape(-1, self.channel)
            self.visphiSC_P2 = self.visphiSC_P2.reshape(-1, self.channel)
            
        if plot:
            for idx in range(len(self.vis2SC_P1)):
                plt.errorbar(self.spFrequAS[idx,:],
                             self.visphiSC_P1[idx,:],
                             self.visphierrSC_P1[idx,:],
                             alpha=0.7, ms=4, lw=0.5, capsize=0,
                             ls='', marker='o',
                             color=self.colors_baseline[idx % 6])
            for idx in range(len(self.vis2SC_P2)):
                plt.errorbar(self.spFrequAS[idx,:],
                             self.visphiSC_P2[idx,:],
                             self.visphierrSC_P2[idx,:],
                             alpha=0.7, ms=4, lw=0.5, capsize=0,
                             ls='', marker='p',
                             color=self.colors_baseline[idx % 6])
            plt.axhline(0, ls='--', lw=0.5)
            plt.xlabel('spatial frequency (1/arcsec)')
            plt.ylabel('visibility phase')
            plt.show()

    def twoD_Gaussian(self, xy, amplitude, xo, yo, sigma_x,
                      sigma_y, theta, offset):
        x, y = xy
        xo = float(xo)
        yo = float(yo)    
        a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
        b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
        c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
        g = offset + amplitude*np.exp( - (a*((x-xo)**2) + 2*b*(x-xo)*(y-yo) 
                                + c*((y-yo)**2)))
        return g.ravel()

    def rotmat(self, x):
        return np.array([[np.cos(x), np.sin(x)], [-np.sin(x), np.cos(x)]])

    def acq_cam_separation(self, guess=[0,0], from_fit=True,
                           only_show=False, plot_fit=True):
        """
        Get the separation from the acq cam image
        """
        acq = fits.open(self.name)['IMAGING_DATA_ACQ'].data[0][:250]
        h = fits.open(self.name)[0].header

        if from_fit:
            ft_string_pre = 'ESO QC ACQ FIELD'
            sc_string_pre = 'ESO QC ACQ FIELD'
            ft_string_pos = ' FT_'
            sc_string_pos = ' SC_'
        else:
            ft_string_pre = 'ESO ACQ FIBER FT'
            sc_string_pre = 'ESO ACQ FIBER SC'
            ft_string_pos = ''
            sc_string_pos = ''
        ftx = [int(round(h[f'{ft_string_pre}{i}{ft_string_pos}X'])) for i in range(1,5)]
        fty = [int(round(h[f'{ft_string_pre}{i}{ft_string_pos}Y'])) for i in range(1,5)]
        if guess == [0,0]:
            scx = [int(round(h[f'{sc_string_pre}{i}{sc_string_pos}X'])) for i in range(1,5)]
            scy = [int(round(h[f'{sc_string_pre}{i}{sc_string_pos}Y'])) for i in range(1,5)]
        else:
            scx = [i+guess[0] for i in ftx]
            scy = [i+guess[1] for i in fty]

        if np.any(np.array(ftx) > 1000):
            ftx = [int(round(h[f'{ft_string_pre}{i}{ft_string_pos}X']
                            - h[f'HIERARCH ESO DET1 FRAM{(i-1)+1} STRX']
                            + (i-1)*250)) for i in range(1,5)]
            fty = [int(round(h[f'{ft_string_pre}{i}{ft_string_pos}Y']
                            - h[f'HIERARCH ESO DET1 FRAM{(i-1)+1} STRY'])) for i in range(1,5)]
            if guess == [0,0]:
                scx = [int(round(h[f'{sc_string_pre}{i}{sc_string_pos}X']
                                - h[f'HIERARCH ESO DET1 FRAM{(i-1)+1} STRX']
                                + (i-1)*250)) for i in range(1,5)]
                scy = [int(round(h[f'{sc_string_pre}{i}{sc_string_pos}Y']
                                - h[f'HIERARCH ESO DET1 FRAM{(i-1)+1} STRY'])) for i in range(1,5)]
            else:
                scx = [i+guess[0] for i in ftx]
                scy = [i+guess[1] for i in fty]


        plt.figure(figsize=(5,7), dpi=300)
        ax = plt.subplot()
        plt.imshow(acq, vmin=0, vmax=np.percentile(acq, 99), origin='lower')
        plt.scatter(ftx, fty, c='r', s=2)
        plt.scatter(scx, scy, c='r', s=2)
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        plt.show()

        if only_show:
            plt.figure(figsize=(4,4), dpi=300)
            ax = plt.subplot()
            plt.imshow(acq[:250,:250], 
                       vmin=np.percentile(acq, 10),
                       vmax=np.percentile(acq, 95), origin='lower')
            plt.scatter(ftx[0], fty[0], c='r', s=10, marker='x')
            plt.scatter(scx[0], scy[0], c='r', s=10, marker='x')
            ax.set_xticklabels([])
            ax.set_yticklabels([])
            plt.show()
        else:
            fcut = 20

            x = np.linspace(0, 2*fcut, 2*fcut+1)
            y = np.linspace(0, 2*fcut, 2*fcut+1)
            x, y = np.meshgrid(x, y)

            fit_ft = np.zeros((4,2))
            fit_sc = np.zeros((4,2))
            for tel in range(4):
                nacq = acq[fty[tel]-fcut:fty[tel]+fcut+1,ftx[tel]-fcut:ftx[tel]+fcut+1]
                initial_guess = (np.max(nacq), fcut, fcut, 5, 5, 0, 100)
                popt, pcov = optimize.curve_fit(self.twoD_Gaussian, (x, y), nacq.flatten(), p0=initial_guess)
                data_fitted = self.twoD_Gaussian((x, y), *popt)

                if plot_fit:
                    fig, ax = plt.subplots(1, 1)
                    plt.imshow(nacq, vmin=0,vmax=np.percentile(nacq, 99), origin='lower')
                    ax.contour(x, y, data_fitted.reshape(2*fcut+1, 2*fcut+1), 4, colors='w')
                    plt.show()

                fit_ft[tel] = np.array(popt[1:3]) - fcut  + np.array([ftx[tel], fty[tel]])

                nacq = acq[scy[tel]-fcut:scy[tel]+fcut+1,scx[tel]-fcut:scx[tel]+fcut+1]
                initial_guess = (np.max(nacq), fcut, fcut, 5, 5, 0, 100)
                popt, pcov = optimize.curve_fit(self.twoD_Gaussian, (x, y), nacq.flatten(), p0=initial_guess)
                data_fitted = self.twoD_Gaussian((x, y), *popt)
                
                if plot_fit:
                    fig, ax = plt.subplots(1, 1)
                    plt.imshow(nacq, vmin=0,vmax=np.percentile(nacq, 99), origin='lower')
                    ax.contour(x, y, data_fitted.reshape(2*fcut+1, 2*fcut+1), 4, colors='w')
                    plt.show()
                fit_sc[tel] = np.array(popt[1:3]) - fcut  + np.array([scx[tel], scy[tel]])
                
            scal = 18
            if h['TELESCOP'] == 'ESO-VLTI-A1234': scal *= 4.44

            vec = (fit_sc - fit_ft) * scal
            res = np.zeros((4,2))
            for tel in range(4):
                a = h[f'ESO QC ACQ FIELD{tel+1} NORTH_ANGLE']
                R = self.rotmat(-a/180*np.pi)
                res[tel] = np.dot(R, vec[tel])
            mres = res.mean(0)
            self.logger.info(f'Separation: [{mres[0]:.0f}, {mres[1]:.0f}]')



    



class GravNight():
    def __init__(self, file_list, loglevel='INFO', onlymet=False):
        """
        GravNight: Class to load several GRAVITY datafiles

        Main functions:
        get_int_data : load all interverometric data into class atributes
        get_met_data : load metrology data
        get_FDDL_data : load FDDL data
        get_acq_data : load data from acquisition camera multiprocessing
        get_faint_timer : get timing from G-Faint files
        """
        log_level = log_level_mapping.get(loglevel, logging.INFO)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        self.file_list = file_list
        self.nfiles = len(file_list)
        self.colors_baseline = np.array(['k', 'darkblue', color4, 
                                         color2, 'darkred', color1])
        self.colors_closure = np.array([color1, 'darkred', 'k', color2])
        self.colors_tel = np.array([color1, 'darkred', 'k', color2])
        self.onlymet = onlymet
        self.get_files()

    def get_files(self):
        self.datalist = []
        self.headerlist = []

        for fi in self.file_list:
            self.datalist.append(GravData(fi, loglevel='ERROR'))
            self.headerlist.append(fits.open(fi)[0].header)
        self.logger.setLevel(self.log_level)

        _catg = [i.datacatg for i in self.datalist]
        if _catg.count(_catg[0]) == len(_catg):
            self.datacatg = _catg[0]
        else:
            self.logger.error(_catg)
            raise ValueError('Not all input data from same category')

        _tel = [i.tel for i in self.datalist]
        if _tel.count(_tel[0]) == len(_tel):
            self.tel = _tel[0]
        else:
            self.logger.error(_tel)
            raise ValueError('Not all input data from same tel')

        _pol = [i.polmode for i in self.datalist]
        if _pol.count(_pol[0]) == len(_pol):
            self.polmode = _pol[0]
        else:
            self.logger.error(_pol)
            self.polmode = None
            if not self.onlymet:
                raise ValueError('Not all input data from same polmode')

        _res = [i.resolution for i in self.datalist]
        if _res.count(_res[0]) == len(_res):
            self.resolution = _res[0]
        else:
            self.logger.error(_res)
            self.resolution = None
            if not self.onlymet:
                raise ValueError('Not all input data from same resolution')

        _dit = [i.dit for i in self.datalist]
        if _dit.count(_dit[0]) == len(_dit):
            self.dit = _dit[0]
        else:
            self.logger.error(_dit)
            self.dit = None
            if not self.onlymet:
                raise ValueError('Not all input data from same dit')

        _ndit = [i.ndit for i in self.datalist]
        if _ndit.count(_ndit[0]) == len(_ndit):
            self.ndit = _ndit[0]
        else:
            self.logger.error(_ndit)
            self.ndit = None
            if not self.onlymet:
                raise ValueError('Not all input data from same ndit')

        self.logger.info(f'{len(self.datalist)} files loaded as:')
        self.logger.info(f'Category: {self.datacatg}')
        self.logger.info(f'Telescope: {self.tel}')
        self.logger.info(f'Polarization: {self.polmode}')
        self.logger.info(f'Resolution: {self.resolution}')
        self.logger.info(f'DIT: {self.dit}')
        self.logger.info(f'NDIT: {self.ndit}')

        self.mjd = [i.mjd for i in self.datalist]
        self.mjd0 = np.min(np.array(self.mjd))
        self.files = [i.name for i in self.datalist]
        self.filenames = [i.filename for i in self.datalist]

    def get_int_data(self, mode='SC', plot=False, plotTAmp=False, flag=False,
                     ignore_tel=[]):
        for data in self.datalist:
            data.get_int_data(mode=mode, plot=plot, plotTAmp=plotTAmp,
                              flag=flag, ignore_tel=ignore_tel)

    def get_time(self):
        files = self.files
        MJD = np.array([]).reshape(0, 4)
        for fdx, file in enumerate(files):
            d = fits.open(file)['OI_FLUX'].data
            _MJD0 = fits.open(file)[0].header['MJD-OBS']
            MJD = np.concatenate((MJD, d['TIME'].reshape(-1, 4)/1e6/3600/24
                                  + _MJD0))
        MJD = (MJD - self.mjd0)*24*60
        self.time = MJD

    def get_met_data(self, plot=False, plotall=False):
        if 'P2VM' not in self.datacatg:
            raise ValueError('Only available for p2vmred files')
        files = self.files

        MJD = np.array([]).reshape(0, 4)
        REFANG = np.array([]).reshape(0, 4)
        OPD_FC = np.array([]).reshape(0, 4)
        OPD_FC_CORR = np.array([]).reshape(0, 4)
        OPD_TEL = np.array([]).reshape(0, 4, 4)
        OPD_TEL_CORR = np.array([]).reshape(0, 4, 4)
        OPD_TELFC_CORR = np.array([]).reshape(0, 4, 4)
        OPD_TELFC_CORR_XY = np.array([]).reshape(0, 4, 4)
        PHA_TELFC_CORR = np.array([]).reshape(0, 4, 4)
        OPD_TELFC_MCORR = np.array([]).reshape(0, 4)
        E_U = np.array([]).reshape(0, 4, 3)
        E_V = np.array([]).reshape(0, 4, 3)

        for fdx, file in enumerate(files):
            h = fits.open(file)[0].header
            d = fits.open(file)['OI_VIS_MET'].data
            ndata = d['TIME'].reshape(-1, 4).shape[0]
            _refang = np.zeros((ndata, 4))
            for tel in range(4):
                _refang[:, tel] = get_refangle(h, tel, ndata)
            REFANG = np.concatenate((REFANG, _refang))
            _MJD0 = fits.open(file)[0].header['MJD-OBS']
            MJD = np.concatenate((MJD,
                                  d['TIME'].reshape(-1, 4)/1e6/3600/24
                                  + _MJD0))
            OPD_FC = np.concatenate((OPD_FC, d['OPD_FC'].reshape(-1, 4)*1e6))
            OPD_FC_CORR = np.concatenate((OPD_FC_CORR, 
                                          d['OPD_FC_CORR'].reshape(-1, 4)*1e6))
            OPD_TELFC_MCORR = np.concatenate((OPD_TELFC_MCORR, 
                                              d['OPD_TELFC_MCORR'].reshape(-1, 4)*1e6))

            E_U = np.concatenate((E_U, d['E_U'].reshape(-1, 4, 3)))
            E_V = np.concatenate((E_V, d['E_V'].reshape(-1, 4, 3)))

            OPD_TEL = np.concatenate((OPD_TEL,
                                      d['OPD_TEL'].reshape(-1, 4, 4)*1e6))
            OPD_TEL_CORR = np.concatenate((OPD_TEL_CORR,
                                           d['OPD_TEL_CORR'].reshape(-1, 4, 4)
                                           * 1e6))
            OPD_TELFC_CORR = np.concatenate((OPD_TELFC_CORR,
                                             d['OPD_TELFC_CORR'].reshape(-1, 4, 4)
                                             * 1e6))
            try:
                OPD_TELFC_CORR_XY = np.concatenate((OPD_TELFC_CORR_XY,
                                             d['OPD_TELFC_CORR_XY'].reshape(-1, 4, 4)
                                             * 1e6))
                PHA_TELFC_CORR = np.concatenate((PHA_TELFC_CORR,
                                             d['PHASE_TELFC_CORR'].reshape(-1, 4, 4)
                                             ))
            except KeyError:
                pass

        MJD = (MJD - self.mjd0)*24*60
        self.time = MJD
        self.refang = REFANG
        self.opd_fc = OPD_FC
        self.opd_fc_corr = OPD_FC_CORR
        self.opd_telfc_mcorr = OPD_TELFC_MCORR
        self.e_u = E_U
        self.e_v = E_V
        self.opd_tel = OPD_TEL
        self.opd_tel_corr = OPD_TEL_CORR
        self.opd_telfc_corr = OPD_TELFC_CORR
        self.opd_telfc_corr_xy = OPD_TELFC_CORR_XY
        self.pha_telfc_corr = PHA_TELFC_CORR
        self.mjd_files = []
        self.ut_files = []
        self.lst_files = []
        for idx, file in enumerate(files):
            d = fits.open(file)
            try:
                self.mjd_files.append(d['OI_VIS', 10].data['MJD'][0])
            except KeyError:
                self.mjd_files.append(d['OI_VIS', 11].data['MJD'][0])
            a = file.find('GRAVI.20')
            self.ut_files.append(file[a+17:a+22])
            self.lst_files.append(d[0].header['LST'])
        self.t_files = (np.array(self.mjd_files)-self.mjd0)*24*60

        if plotall or plot == 'TEL':
            # OPD TEL
            av = 100
            maxval = []
            for tel in range(4):
                for dio in range(4):
                    maxval.append(np.nanmax(np.abs(
                        averaging(OPD_TEL[:, tel, dio]
                                  - np.nanmean(OPD_TEL[:, tel, dio]), av))))
            maxval = np.max(maxval)*1.2

            gs = gridspec.GridSpec(4, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 7))
            for tel in range(4):
                for dio in range(4):
                    ax = plt.subplot(gs[tel, dio])
                    plt.plot(averaging(MJD[:, tel], av),
                             averaging(OPD_TEL[:, tel, dio]
                                       - np.mean(OPD_TEL[:, tel, dio]), av),
                             ls='', marker='.', color=self.colors_tel[tel],
                             label='%s%i\nDiode %i' % (self.tel,(4-tel), dio))
                    for m in range(len(self.t_files)):
                        plt.axvline(self.t_files[m], ls='--', lw=0.2,
                                    color='grey')
                        if tel == 0 and dio == 0:
                            plt.text(self.t_files[m]+0.5, -maxval*0.9,
                                     self.ut_files[m], rotation=90, fontsize=5)
                    plt.legend(loc=2)
                    plt.ylim(-maxval, maxval)
                    if tel != 3:
                        ax.set_xticklabels([])
                    else:
                        plt.xlabel('Time [mins]', fontsize=8)
                    if dio != 0:
                        ax.set_yticklabels([])
                    else:
                        plt.ylabel('OPD_TEL \n[$\mu$m]', fontsize=8)
            plt.show()

        if plotall or plot == 'TEL_CORR':
            # OPD TEL CORR
            av = 100
            maxval = []
            for tel in range(4):
                for dio in range(4):
                    maxval.append(np.nanmax(np.abs(
                        averaging(OPD_TEL_CORR[:, tel, dio]
                                  - np.mean(OPD_TEL_CORR[:, tel, dio]), av))))
            maxval = np.max(maxval)*1.2

            gs = gridspec.GridSpec(4, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 7))
            for tel in range(4):
                for dio in range(4):
                    ax = plt.subplot(gs[tel, dio])
                    plt.plot(averaging(MJD[:, tel], av),
                             averaging(OPD_TEL_CORR[:, tel, dio]
                                       - np.mean(OPD_TEL_CORR[:, tel, dio]), av),
                             ls='', marker='.', color=self.colors_tel[tel],
                             label='%s%i\nDiode %i' % (self.tel, (4-tel), dio))
                    for m in range(len(self.t_files)):
                        plt.axvline(self.t_files[m], ls='--', lw=0.2,
                                    color='grey')
                        if tel == 0 and dio == 0:
                            plt.text(self.t_files[m]+0.5, -maxval*0.9,
                                     self.ut_files[m], rotation=90, fontsize=5)
                    plt.legend(loc=2)
                    plt.ylim(-maxval, maxval)
                    if tel != 3:
                        ax.set_xticklabels([])
                    else:
                        plt.xlabel('Time [mins]', fontsize=8)
                    if dio != 0:
                        ax.set_yticklabels([])
                    else:
                        plt.ylabel('OPD_TEL_CORR \n[$\mu$m]', fontsize=8)
            plt.show()

        if plotall or plot == 'TELFC_CORR':
            # OPD TEL FC CORR
            av = 100
            maxval = []
            for tel in range(4):
                for dio in range(4):
                    maxval.append(np.nanmax(np.abs(
                        averaging(OPD_TELFC_CORR[:, tel, dio]
                                  - np.mean(OPD_TELFC_CORR[:, tel, dio]), av))))
            maxval = np.max(maxval)*1.2

            gs = gridspec.GridSpec(4, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 7))
            for tel in range(4):
                for dio in range(4):
                    ax = plt.subplot(gs[tel, dio])
                    plt.plot(averaging(MJD[:, tel], av),
                             averaging(OPD_TELFC_CORR[:, tel, dio]
                                       - np.mean(OPD_TELFC_CORR[:, tel, dio]), av),
                             ls='', marker='.', color=self.colors_tel[tel],
                             label='%s%i\nDiode %i' % (self.tel,(4-tel), dio))
                    for m in range(len(self.t_files)):
                        plt.axvline(self.t_files[m], ls='--', lw=0.2,
                                    color='grey')
                        if tel == 0 and dio == 0:
                            plt.text(self.t_files[m]+0.5, -maxval*0.9,
                                     self.ut_files[m], rotation=90, fontsize=5)
                    plt.legend(loc=2)
                    plt.ylim(-maxval, maxval)
                    if tel != 3:
                        ax.set_xticklabels([])
                    else:
                        plt.xlabel('Time [mins]', fontsize=8)
                    if dio != 0:
                        ax.set_yticklabels([])
                    else:
                        plt.ylabel('OPD_TELFC_CORR \n[$\mu$m]', fontsize=8)
            plt.show()

        if plotall or plot == 'FC':
            # OPD_FC
            maxval = []
            for tel in range(4):
                maxval.append(np.nanmax(np.abs(
                    averaging(OPD_FC[:, tel]
                              - np.mean(OPD_FC[:, tel]), av))))
            maxval = np.max(maxval)*1.2
            gs = gridspec.GridSpec(1, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 2))
            for tel in range(4):
                ax = plt.subplot(gs[0, tel])
                plt.plot(averaging(MJD[:, tel], av),
                         averaging(OPD_FC[:, tel]
                                   - np.mean(OPD_FC[:, tel]), av),
                         ls='', marker='.', label='%s%i' % (self.tel, (4-tel)),
                         color=self.colors_tel[tel])
                for m in range(len(self.t_files)):
                    plt.axvline(self.t_files[m], ls='--', lw=0.2, color='grey')
                    if tel == 0:
                        plt.text(self.t_files[m]+0.5, -maxval*0.9,
                                 self.ut_files[m], rotation=90, fontsize=5)
                plt.legend(loc=2)
                plt.ylim(-maxval, maxval)
                plt.xlabel('Time [mins]', fontsize=8)
                if tel != 0:
                    ax.set_yticklabels([])
                else:
                    plt.ylabel('OPD_FC \n[$\mu$m]', fontsize=8)
            plt.show()

            # OPD_FC_CORR
        if plotall or plot == 'FC_CORR':
            maxval = []
            for tel in range(4):
                maxval.append(np.nanmax(np.abs(
                    averaging(OPD_FC_CORR[:, tel]
                              - np.mean(OPD_FC_CORR[:, tel]), av))))
            maxval = np.max(maxval)*1.2
            gs = gridspec.GridSpec(1, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 2))
            for tel in range(4):
                ax = plt.subplot(gs[0, tel])
                plt.plot(averaging(MJD[:, tel], av),
                         averaging(OPD_FC_CORR[:, tel]
                                   - np.mean(OPD_FC_CORR[:, tel]), av),
                         ls='', marker='.', label='%s%i' % (self.tel, (4-tel)),
                         color=self.colors_tel[tel])
                for m in range(len(self.t_files)):
                    plt.axvline(self.t_files[m], ls='--', lw=0.2, color='grey')
                    if tel == 0:
                        plt.text(self.t_files[m]+0.5, -maxval*0.9,
                                 self.ut_files[m], rotation=90, fontsize=5)
                plt.legend(loc=2)
                plt.ylim(-maxval, maxval)
                plt.xlabel('Time [mins]', fontsize=8)
                if tel != 0:
                    ax.set_yticklabels([])
                else:
                    plt.ylabel('OPD_FC_CORR \n[$\mu$m]', fontsize=8)
            plt.show()

        if plot or plotall:
            av = 500
            maxval = []
            for tel in range(4):
                maxval.append(np.nanmax(np.abs(
                    averaging(OPD_TELFC_MCORR[:, tel]
                              - np.mean(OPD_TELFC_MCORR[:, tel]), av))))
            maxval = np.max(maxval)*1.2
            gs = gridspec.GridSpec(1, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 2))
            for tel in range(4):
                ax = plt.subplot(gs[0, tel])
                plt.plot(averaging(MJD[:, tel], av),
                         averaging(OPD_TELFC_MCORR[:, tel]
                                   - np.mean(OPD_TELFC_MCORR[:, tel]), av),
                         ls='', marker='.', label='%s%i' % (self.tel, (4-tel)),
                         color=self.colors_tel[tel])
                for m in range(len(self.t_files)):
                    plt.axvline(self.t_files[m], ls='--', lw=0.2, color='grey')
                    if tel == 0:
                        plt.text(self.t_files[m]+0.5, -maxval*0.9,
                                 self.ut_files[m], rotation=90, fontsize=5)
                plt.legend(loc=2)
                plt.ylim(-maxval, maxval)
                plt.xlabel('Time [mins]', fontsize=8)
                if tel != 0:
                    ax.set_yticklabels([])
                else:
                    plt.ylabel('OPD_TELFC_MCORR \n[$\mu$m]', fontsize=8)
            plt.show()

    def get_FDDL_data(self, plot=False):
        if 'P2VM' not in self.datacatg:
            raise ValueError('Only available for p2vmred files')
        if self.polmode == 'SPLIT':
            fitnum = 11
        else:
            fitnum = 10
        files = self.files
        MJD = np.array([]).reshape(0, 4)
        FT_POS = np.array([]).reshape(0, 4)
        SC_POS = np.array([]).reshape(0, 4)

        for fdx, file in enumerate(files):
            d = fits.open(file)['FDDL'].data
            _MJD0 = fits.open(file)[0].header['MJD-OBS']
            _t = np.tile(d['TIME'], (4, 1)).T
            MJD = np.concatenate((MJD, _t/1e6/3600/24 + _MJD0))
            FT_POS = np.concatenate((FT_POS, d['FT_POS']))
            SC_POS = np.concatenate((SC_POS, d['SC_POS']))
        MJD = (MJD - self.mjd0)*24*60
        self.fddltime = MJD
        self.fddl = np.array([FT_POS, SC_POS])
        self.mjd_files = []
        self.ut_files = []
        self.lst_files = []
        for idx, file in enumerate(files):
            d = fits.open(file)
            self.mjd_files.append(d['OI_VIS', fitnum].data['MJD'][0])
            a = file.find('GRAVI.20')
            self.ut_files.append(file[a+17:a+22])
            self.lst_files.append(d[0].header['LST'])
        self.t_files = (np.array(self.mjd_files)-self.mjd0)*24*60

        if plot:
            maxval = np.nanmax(self.fddl)*1.1
            minval = np.nanmin(self.fddl)*1.1
            fddl_name = ['FT', 'SC']

            gs = gridspec.GridSpec(2, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 5))
            for fddl in range(2):
                for tel in range(4):
                    ax = plt.subplot(gs[fddl, tel])
                    plt.plot(self.fddltime[:, tel],
                             self.fddl[fddl, :, tel],
                             ls='', marker='.',  markersize=1,
                             color=self.colors_tel[tel])
                    for m in range(len(self.t_files)):
                        plt.axvline(self.t_files[m], ls='--', lw=0.2,
                                    color='grey')
                        if tel == 0 and fddl == 0:
                            plt.text(self.t_files[m]+0.5, minval+minval*0.1,
                                     self.ut_files[m], rotation=90, fontsize=5)
                    plt.ylim(minval, maxval)
                    if fddl == 0:
                        plt.title('%s %i' % (self.tel, (4-tel)), fontsize=8)
                    if fddl != 1:
                        ax.set_xticklabels([])
                    else:
                        plt.xlabel('Time [mins]', fontsize=8)
                    if tel != 0:
                        ax.set_yticklabels([])
                    else:
                        plt.ylabel('FDDL %s\n[V]' % fddl_name[fddl],
                                   fontsize=8)
            plt.show()

    def get_acq_data(self, plot=False):
        if 'P2VM' not in self.datacatg:
            raise ValueError('Only available for p2vmred files')
        files = self.files
        if self.polmode == 'SPLIT':
            fitnum = 11
        else:
            fitnum = 10

        MJD = np.array([]).reshape(0, 4)
        PUPIL_U = np.array([]).reshape(0, 4)
        PUPIL_V = np.array([]).reshape(0, 4)
        PUPIL_W = np.array([]).reshape(0, 4)

        for fdx, file in enumerate(files):
            d = fits.open(file)['OI_VIS_ACQ'].data
            _MJD0 = fits.open(file)[0].header['MJD-OBS']
            MJD = np.concatenate((MJD,
                                  d['TIME'].reshape(-1, 4)/1e6/3600/24 + _MJD0))
            PUPIL_U = np.concatenate((PUPIL_U, d['PUPIL_U'].reshape(-1, 4)))
            PUPIL_V = np.concatenate((PUPIL_V, d['PUPIL_V'].reshape(-1, 4)))
            PUPIL_W = np.concatenate((PUPIL_W, d['PUPIL_W'].reshape(-1, 4)))

        MJD = (MJD - self.mjd0)*24*60
        self.acqtime = MJD
        self.pupil = np.array([PUPIL_U, PUPIL_V, PUPIL_W])
        self.pupil[self.pupil == 0] = np.nan
        self.mjd_files = []
        self.ut_files = []
        self.lst_files = []
        for idx, file in enumerate(files):
            d = fits.open(file)
            try:
                self.mjd_files.append(d['OI_VIS', 10].data['MJD'][0])
            except KeyError:
                self.mjd_files.append(d['OI_VIS', 11].data['MJD'][0])
            a = file.find('GRAVI.20')
            self.ut_files.append(file[a+17:a+22])
            self.lst_files.append(d[0].header['LST'])
        self.t_files = (np.array(self.mjd_files)-self.mjd0)*24*60

        if plot:
            maxval = np.nanmax(np.abs(self.pupil), (1,2))*1.1
            pup_name = ['U', 'V', 'W']

            gs = gridspec.GridSpec(3, 4, wspace=0.05, hspace=0.05)
            plt.figure(figsize=(7, 7))
            for pup in range(3):
                for tel in range(4):
                    ax = plt.subplot(gs[pup, tel])
                    plt.plot(self.acqtime[:, tel], self.pupil[pup, :, tel],
                             ls='', marker='.',  markersize=1,
                             color=self.colors_tel[tel])
                    for m in range(len(self.t_files)):
                        plt.axvline(self.t_files[m], ls='--', lw=0.2,
                                    color='grey')
                        if tel == 0 and pup == 0:
                            plt.text(self.t_files[m]+0.5, -maxval[pup]*0.9,
                                     self.ut_files[m], rotation=90, fontsize=5)
                    plt.ylim(-maxval[pup], maxval[pup])
                    plt.axhline(0, ls='--', lw=1, zorder=0, color='grey')
                    if pup == 0:
                        plt.title('%s %i' % (self.tel, (4-tel)), fontsize=8)
                    if pup != 2:
                        ax.set_xticklabels([])
                    else:
                        plt.xlabel('Time [mins]', fontsize=8)
                    if tel != 0:
                        ax.set_yticklabels([])
                    else:
                        plt.ylabel('PUPIL %s\n[m]' % pup_name[pup],
                                   fontsize=8)
            plt.show()

    def get_faint_timer(self):
        files = self.files
        onv = np.array([])
        ofv = np.array([])

        self.faintprop = []
        for file in files:
            h = fits.open(file)[0].header
            if h['ESO INS MET MODE'] != 'FAINT':
                raise ValueError('Metmode is not faint')
            rate1 = h['ESO INS ANLO3 RATE1']/60
            rate2 = h['ESO INS ANLO3 RATE2']/60
            repe1 = h['ESO INS ANLO3 REPEAT1']
            repe2 = h['ESO INS ANLO3 REPEAT2']
            time1 = h['ESO INS ANLO3 TIMER1']
            time2 = h['ESO INS ANLO3 TIMER2']
            volt1 = h['ESO INS ANLO3 VOLTAGE1']
            volt2 = h['ESO INS ANLO3 VOLTAGE2']
            
            self.logger.info(f'Bright period: {rate1*60-(time2-time1):.2f}, '
                             f'Voltage: {volt1:.1f}, {volt2:.1f}')
            self.faintprop.append([rate1*60-(time2-time1), volt1, volt2])

            mt1 = ((time1 / 86400.0) + 2440587.5 - 2400000.5 - self.mjd0)*24*60
            mt2 = ((time2 / 86400.0) + 2440587.5 - 2400000.5 - self.mjd0)*24*60

            onv = np.concatenate((onv, np.linspace(mt1, mt1+rate1*(repe1-1),
                                                   repe1)))
            ofv = np.concatenate((ofv, np.linspace(mt2, mt2+rate2*(repe2-1),
                                                   repe2)))

        try:
            self.onv = np.concatenate((onv, np.array([self.time[-1, 0]])))
            self.ofv = np.concatenate((np.array([self.time[0, 0]]), ofv))
        except AttributeError:
            try:
                self.get_met_data()
                self.onv = np.concatenate((onv, np.array([self.time[-1, 0]])))
                self.ofv = np.concatenate((np.array([self.time[0, 0]]), ofv))
            except ValueError:
                self.ofv = np.concatenate((np.array([0]), ofv))
                self.onv = np.concatenate((onv, np.array([ofv[-1] + ofv[0]])))

    def plot_sep_tracking(self, plot=True):
        def get_data(l, string, mjd0=None):
            dat = [t for t in l if string in t]
            pos = np.array([np.fromstring(s[s.find('[mas]')+7:], sep=' ', dtype=float) for s in dat])
            mjd = [convert_date(s[s.find(night[:-2]):s.find(night[:-2])+19]
                                   + '.' + s[s.find(night[:-2])+20:s.find(night[:-2])+23], mjd=True)
                           for s in dat]
            if mjd0 is not None:
                mjd = [(d - mjd0)*24*60 for d in mjd]
            return mjd, pos

        def get_rms(l, mjd0=None):
            pos = []
            mjd = []
            for tel in range(4):
                string = f'Telescope {tel} rms diodes'
                dat = [t for t in l if string in t]

                pos.append(np.array([np.fromstring(s[s.find('rms diodes')+12:-4], sep=', ', dtype=float) for s in dat]))
                _mjd = [convert_date(s[s.find(night[:-2]):s.find(night[:-2])+19]
                                        + '.' + s[s.find(night[:-2])+20:s.find(night[:-2])+23], mjd=True)
                               for s in dat]
                if mjd0 is not None:
                    _mjd = [(d - mjd0)*24*60 for d in _mjd]
                mjd.append(_mjd)
            return mjd, pos

        d = convert_date(fits.open(self.files[0])[0].header['DATE-OBS'])[1]
        lognight = str(d + timedelta(hours=12) - timedelta(days=1))[:10]
        night = str(d + timedelta(hours=12))[:10]
        start = str(d - timedelta(minutes=5))[11:-3]

        d = convert_date(fits.open(self.files[-1])[0].header['DATE-OBS'])[1]
        stop = str(d + timedelta(minutes=10))[11:-3]

        log = f'/tera/3/wgvLogFiles/wgv.{lognight}.log'
        with open(log, 'rb') as f:
            output = f.readlines()
        toutput = [str(o)[2:-3] for o in output]
        toutput = [t for t in toutput if 'gvkalmPyProcessing' in t]

        _sta = [tdx for tdx, t in enumerate(toutput)
                if f'{night} {start}' in t][0]
        _sto = [tdx for tdx, t in enumerate(toutput)
                if f'{night} {stop}' in t][0]

        toutput = toutput[_sta:_sto]

        mjd, _ = get_data(toutput, 'KAL separation X v2')

        mjd0 = mjd[0]

        t_kalX, kalX = get_data(toutput, 'KAL separation X v2', mjd0=mjd0)
        t_kalY, kalY = get_data(toutput, 'KAL separation Y v2', mjd0=mjd0)
        t_kalX2, kalX2 = get_data(toutput, 'KAL separation X v3', mjd0=mjd0)
        t_kalY2, kalY2 = get_data(toutput, 'KAL separation Y v3', mjd0=mjd0)

        t_ctuX, ctuX = get_data(toutput, 'CTU separation X', mjd0=mjd0)
        t_ctuY, ctuY = get_data(toutput, 'CTU separation Y', mjd0=mjd0)

        t_appX, appX = get_data(toutput, 'Applied Xoffset', mjd0=mjd0)
        t_appY, appY = get_data(toutput, 'Applied Yoffset', mjd0=mjd0)

        t_meaX, meaX = get_data(toutput, 'Measured Xoffset', mjd0=mjd0)
        t_meaY, meaY = get_data(toutput, 'Measured Yoffset', mjd0=mjd0)

        t_sep, sep = get_data(toutput, 'Header separation', mjd0=mjd0)

        t_rms, rms = get_rms(toutput,  mjd0=mjd0)

        colors = ['C0', 'C3', 'C2', 'darkblue']
        plt.figure(figsize=(10,6))
        gs = gridspec.GridSpec(4,2, hspace=0.05, wspace=0.3)
        for tel in range(4):
            ax = plt.subplot(gs[tel,0])
            plt.plot(t_kalX, kalX[:,tel], color=colors[tel], label=f'Beam {tel+1}')
            plt.plot(t_kalX2, kalX2[:,tel], color=colors[tel], ls='--', label=f'Beam {tel+1}, w/o astigm')
            plt.plot(t_ctuX, ctuX[:,tel], color='k', label='CTU')
            plt.plot(t_sep, sep[:,0]*1e3, color='grey', label='Header val')
            
            plt.legend(fontsize=7, frameon=True, loc=4)
            if tel == 3:
                plt.xlabel(f'Time since {start} in min')
            else:
                ax.set_xticklabels([])

            plt.ylabel('X separation')

            ax = plt.subplot(gs[tel,1])
            plt.plot(t_kalY, kalY[:,tel], color=colors[tel])
            plt.plot(t_kalY2, kalY2[:,tel], color=colors[tel])
            plt.plot(t_ctuY, ctuY[:,tel], color='k')
            plt.ylabel('Y separation')
            plt.plot(t_sep, sep[:,1]*1e3, color='grey')
            if tel == 3:
                plt.xlabel(f'Time since {start} in min')
            else:
                ax.set_xticklabels([])
        plt.show()

        colors = ['C0', 'C3', 'C2', 'darkblue']
        plt.figure(figsize=(10,6))
        gs = gridspec.GridSpec(4,2, hspace=0.05, wspace=0.3)
        for tel in range(4):
            ax = plt.subplot(gs[tel,0])
            plt.plot(t_kalX, kalX[:,tel]-interpolate.interp1d(t_sep, sep[:,0]*1e3, fill_value='extrapolate')(t_kalX),
                     color=colors[tel], label=f'Beam {tel+1}')
            plt.plot(t_kalX2, kalX2[:,tel]-interpolate.interp1d(t_sep, sep[:,0]*1e3, fill_value='extrapolate')(t_kalX2),
                     color=colors[tel], ls='--', label=f'Beam {tel+1}, w/o astigm')
            plt.plot(t_ctuX, ctuX[:,tel]-interpolate.interp1d(t_sep, sep[:,0]*1e3, fill_value='extrapolate')(t_ctuX),
                     color='k', label='CTU')
            plt.legend(fontsize=7, frameon=True, loc=4)
            if tel == 3:
                plt.xlabel(f'Time since {start} in min')
            else:
                ax.set_xticklabels([])
            ax.set_ylim(-110,110)
            plt.ylabel('X separation\nrel. to header')

            ax = plt.subplot(gs[tel,1])
            plt.plot(t_kalY, kalY[:,tel]-interpolate.interp1d(t_sep, sep[:,1]*1e3, fill_value='extrapolate')(t_kalY),
                     color=colors[tel], label=f'Beam {tel+1}')
            plt.plot(t_kalY2, kalY2[:,tel]-interpolate.interp1d(t_sep, sep[:,1]*1e3, fill_value='extrapolate')(t_kalY2),
                     color=colors[tel], ls='--', label=f'Beam {tel+1}, w/o astigm')
            plt.plot(t_ctuY, ctuY[:,tel]-interpolate.interp1d(t_sep, sep[:,1]*1e3, fill_value='extrapolate')(t_ctuY),
                     color='k', label='CTU')
            plt.ylabel('Y separation\nrel. to header')
            if tel == 3:
                plt.xlabel(f'Time since {start} in min')
            else:
                ax.set_xticklabels([])
            ax.set_ylim(-110,110)
        plt.show()

        gs = gridspec.GridSpec(2,2, hspace=0.05, wspace=0.25
                              )
        for tel in range(4):
            ax = plt.subplot(gs[tel//2,tel%2])
            _rms = np.copy(rms[tel])
            _rms_all = np.copy(rms[tel])
            _rms[_rms==0] = np.nan
            _rms[_rms>1] = np.nan
            _rms_all[_rms_all==0] = np.nan
            plt.plot(t_rms[tel], _rms_all, color=colors[tel], alpha=0.1)
            plt.plot(t_rms[tel], _rms, color=colors[tel], alpha=0.8)
            plt.axhline(1, lw=0.5, ls='--', color='grey')
            if tel//2 == 1:
                plt.xlabel(f'Time since {start} in min')
            else:
                ax.set_xticklabels([])
            plt.ylabel(f'RMS Beam {tel+1}')
            ax.set_ylim(0, 1.9)
        plt.show()


        _appX = np.copy(appX)
        _appX[_appX == 0] = np.nan
        _appY = np.copy(appY)
        _appY[_appY == 0] = np.nan

        _meaX = np.copy(meaX)
        _meaX[_meaX == 0] = np.nan
        _meaY = np.copy(meaY)
        _meaY[_meaY == 0] = np.nan

        off = 0.04

        gs = gridspec.GridSpec(2,1, hspace=0.05)
        ax = plt.subplot(gs[0,0])
        for tel in range(4):
            plt.plot(t_appX, _appX[:,tel]+off*(3-tel), color=colors[tel], marker='o', ms=2, ls='')
            plt.plot(t_meaX, _meaX[:,tel]+off*(3-tel), color=colors[tel], marker='x', ms=3, ls='')
            plt.axhline(off*(3-tel), lw=0.5, ls='--', color=colors[tel])
            plt.text(-5, off*(3-tel)-off/3, f'Beam {tel+1}', fontsize=8, color=colors[tel])
        ax.set_xticklabels([])
        plt.ylabel('applied X separation')
        plt.xlim(left=-10)
        plt.ylim(-0.05,0.15)

        ax = plt.subplot(gs[1,0])
        for tel in range(4):
            plt.plot(t_appY, _appY[:,tel]+off*(3-tel), color=colors[tel], marker='o', ms=2, ls='')
            plt.plot(t_meaY, _meaY[:,tel]+off*(3-tel), color=colors[tel], marker='x', ms=3, ls='')
            plt.axhline(off*(3-tel), lw=0.5, ls='--', color=colors[tel])
            plt.text(-5, off*(3-tel)-off/3, f'Beam {tel+1}', fontsize=8, color=colors[tel])
        plt.xlabel(f'Time since {start} in min')
        plt.ylabel('applied Y separation')
        plt.xlim(left=-10)
        plt.ylim(-0.05, 0.15)
        plt.show()

    def plot_visphi(self, nicer=True, ymin=None, ymax=None):
        self.get_int_data()
        plt.figure(figsize=(8, self.nfiles*1))
        gs = gridspec.GridSpec(self.nfiles, 2, hspace=0.05,
                               wspace=0.01)

        # maybe make this for all, for now it's only phase
        plot_quant = ['Visamp', 'Vis2', 'Closure Phase', 'Visibility Phase']
        plot_closure = [0, 0, 1, 0]
        plot_min = [-0.03, -0.03, -180, -180]
        plot_max = [1.1, 1.1, 180, 180]
        plot_text = [-0.07, -0.07, -180*1.06, -180*1.3]
        pdx = 3
        if ymin is None: ymin = plot_min[pdx]
        if ymax is None: ymax = plot_max[pdx]

        for ndx in range(self.nfiles):
            obj = self.datalist[ndx]
            _fn = obj.filename
            spf = obj.spFrequAS

            ax = plt.subplot(gs[ndx, 0])
            x = spf
            val = obj.visphiSC_P1
            err = obj.visphierrSC_P1
            flag = obj.visphiflagSC_P1
            if val.shape[0] > 6:
                val = val.reshape(-1,6,len(x[0]))
                err = err.reshape(-1,6,len(x[0]))
                flag = flag.reshape(-1,6,len(x[0]))
                spf = spf.reshape(-1,6,len(x[0]))
            if nicer:
                bl_sort = [2, 3, 5, 0, 4, 1]
                nchannel = val.shape[-1]
                x = np.zeros((6, nchannel))
                for bl in range(6):
                    x[bl] = (np.linspace(nchannel, 0, nchannel)
                               + bl_sort[bl]*(nchannel+nchannel//2))
            else:
                x = spf
            ax = plt.subplot(gs[ndx, 0])
            colors = obj.colors_baseline
            labels = obj.baseline_labels
            prange = 6
            for i in range(prange):
                if val.ndim == 3:
                    for dit in range(self.ndit):
                        plt.errorbar(x[i, :],
                            val[dit, i, :]*(1-flag)[dit, i],
                            err[dit, i, :]*(1-flag)[dit, i],
                            color=colors[i],
                            marker='.',
                            ls='', lw=1, alpha=0.5, capsize=0)


                else:
                    plt.errorbar(x[i, :],
                                 val[i, :]*(1-flag)[i],
                                 err[i, :]*(1-flag)[i],
                                 color=colors[i],
                                marker='.',
                                ls='', lw=1, alpha=1, capsize=0)
                #plt.scatter(x[i, :],
                #            val[i, :]*(1-flag)[i],
                #            color=colors[i],
                #            alpha=0.5)
                if nicer and ndx == self.nfiles - 1:
                    plt.text(x[i, :].mean(), ymin*1.3,
                             labels[i],
                             color=colors[i],
                             ha='center', va='center',
                             fontsize=8)
            plt.text(0.02, 0.88, f'File {ndx+1}/{self.nfiles}, {_fn[_fn.find("T")+1:_fn.find("T")+6]}',
                     transform=ax.transAxes, fontsize=7,
                     horizontalalignment='left')
            plt.axhline(0, lw=0.5, ls='--', color='grey')
            plt.yticks(fontsize=6)
            plt.ylim(ymin, ymax)
            if nicer:
                # ax.set_xticklabels([])
                ax.set_xticks([])
                if ndx == 0:
                    plt.title(f'{plot_quant[pdx]}, P1', fontsize=9)
            else:
                plt.ylabel(plot_quant[pdx])
                if ndx > self.nfiles - 1:
                    plt.xlabel('spatial frequency (1/arcsec)')
                else:
                    ax.set_xticks([])

            ax = plt.subplot(gs[ndx, 1])
            val = obj.visphiSC_P2
            err = obj.visphierrSC_P2
            flag = obj.visphiflagSC_P2
            if val.shape[0] > 6:
                val = val.reshape(-1,6,len(x[0]))
                err = err.reshape(-1,6,len(x[0]))
                flag = flag.reshape(-1,6,len(x[0]))



            for i in range(prange):
                if val.ndim == 3:
                    for dit in range(self.ndit):
                        plt.errorbar(x[i, :],
                            val[dit, i, :]*(1-flag)[dit, i],
                            err[dit, i, :]*(1-flag)[dit, i],
                            color=colors[i],
                            marker='.',
                            ls='', lw=1, alpha=0.5, capsize=0)


                else:
                    plt.errorbar(x[i, :],
                                val[i, :]*(1-flag)[i],
                                err[i, :]*(1-flag)[i],
                                color=colors[i],
                                marker='.',
                                ls='', lw=1, alpha=1, capsize=0)
                #plt.scatter(x[i, :],
                #            val[i, :]*(1-flag)[i],
                #            color=colors[i],
                #            alpha=0.5)
                if nicer and ndx == self.nfiles - 1:
                    plt.text(x[i, :].mean(), ymin*1.3,
                             labels[i],
                             color=colors[i],
                             ha='center', va='center',
                             fontsize=8)
            plt.axhline(0, lw=0.5, ls='--', color='grey')
            ax.set_yticklabels([])
            plt.yticks(fontsize=8)
            plt.ylim(ymin, ymax)
            if nicer:
                # ax.set_xticklabels([])
                ax.set_xticks([])
                if ndx == 0:
                    plt.title(f'{plot_quant[pdx]}, P2', fontsize=9)
            else:
                plt.ylabel(plot_quant[pdx])
                if ndx > self.nfiles - 1:
                    plt.xlabel('spatial frequency (1/arcsec)')
                else:
                    ax.set_xticks([])
        plt.show()
