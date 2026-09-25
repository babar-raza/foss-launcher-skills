import com.aspose.threed.NurbsCurve;
import com.aspose.threed.Vector4;

NurbsCurve curve = new NurbsCurve("profile");
curve.setDegree(3);
curve.getControlPoints().add(new Vector4(0, 0, 0, 1));
curve.getControlPoints().add(new Vector4(1, 2, 0, 1));
curve.getControlPoints().add(new Vector4(2, 0, 0, 1));
